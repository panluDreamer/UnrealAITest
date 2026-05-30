// Copyright Epic Games, Inc. All Rights Reserved.

#include "UnrealEngineAIAssistModule.h"
#include "Modules/ModuleManager.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "HAL/RunnableThread.h"
#include "Interfaces/IPv4/IPv4Address.h"
#include "Interfaces/IPv4/IPv4Endpoint.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonWriter.h"
#include "Async/Async.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "Misc/EngineVersion.h"
#include "HAL/PlatformFilemanager.h"
#include "UObject/UObjectIterator.h"
#include "UObject/Class.h"
#include "UObject/UnrealType.h"
#include "UObject/TextProperty.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"

// Soft dependency on PythonScriptPlugin — HAS_PYTHON_SCRIPT_PLUGIN is defined by Build.cs
#if HAS_PYTHON_SCRIPT_PLUGIN
#include "IPythonScriptPlugin.h"
#endif

#include "Interfaces/IPluginManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogAIAssist, Log, All);

// ============================================================================
// Agent directory name helper — supports multiple AI clients
// ============================================================================

static FString GetAgentDirName()
{
	// 1. Check AGENT_DIR_NAME environment variable
	FString EnvVal = FPlatformMisc::GetEnvironmentVariable(TEXT("AGENT_DIR_NAME"));
	if (!EnvVal.IsEmpty())
	{
		return EnvVal;
	}
	// 2. Fallback
	return TEXT(".claude");
}

static UObject* FindObjectByNameOrPath(const FString& ObjectPath)
{
	UObject* Obj = StaticFindObject(UObject::StaticClass(), nullptr, *ObjectPath);
	if (!Obj)
	{
		Obj = FindFirstObjectSafe<UObject>(*ObjectPath, EFindFirstObjectOptions::NativeFirst);
	}
	return Obj;
}

static UClass* FindClassByNameOrPath(const FString& ClassOrObjectPath)
{
	TArray<FString> Candidates;
	Candidates.Add(ClassOrObjectPath);

	if (ClassOrObjectPath.Len() > 1 &&
		(ClassOrObjectPath.StartsWith(TEXT("U")) || ClassOrObjectPath.StartsWith(TEXT("A"))))
	{
		Candidates.Add(ClassOrObjectPath.Mid(1));
	}
	Candidates.Add(TEXT("U") + ClassOrObjectPath);
	Candidates.Add(TEXT("A") + ClassOrObjectPath);

	for (const FString& Candidate : Candidates)
	{
		UClass* TargetClass = FindObject<UClass>(nullptr, *Candidate);
		if (!TargetClass)
		{
			TargetClass = FindFirstObjectSafe<UClass>(*Candidate, EFindFirstObjectOptions::NativeFirst);
		}
		if (TargetClass)
		{
			return TargetClass;
		}
	}

	UObject* Obj = FindObjectByNameOrPath(ClassOrObjectPath);
	return Obj ? Obj->GetClass() : nullptr;
}

// ============================================================================
// Plugin directory resolution — decoupled from Engine path
// ============================================================================

void FUnrealEngineAIAssistModule::InitPluginDir()
{
	// Find the .uplugin file by walking up from the module's binary directory.
	// IPluginManager could be used, but this is simpler and works pre-PostEngineInit.
	TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("UnrealEngineAIAssist"));
	if (Plugin.IsValid())
	{
		PluginDir = FPaths::ConvertRelativePathToFull(Plugin->GetBaseDir());
	}
	else
	{
		// Fallback: derive from known module file location
		// Module DLL is at Binaries/Win64/UE4Editor-UnrealEngineAIAssist.dll (or similar)
		// Plugin root is several levels up. Use the .uplugin search approach instead.
		FString SearchDir = FPaths::ConvertRelativePathToFull(FPaths::EnginePluginsDir());
		FString TestPath = SearchDir / TEXT("UnrealEngineAIAssist") / TEXT("UnrealEngineAIAssist.uplugin");
		if (FPaths::FileExists(TestPath))
		{
			PluginDir = SearchDir / TEXT("UnrealEngineAIAssist");
		}
		else
		{
			// Last resort: check project plugins
			FString ProjectPlugins = FPaths::ConvertRelativePathToFull(FPaths::ProjectPluginsDir());
			TestPath = ProjectPlugins / TEXT("UnrealEngineAIAssist") / TEXT("UnrealEngineAIAssist.uplugin");
			if (FPaths::FileExists(TestPath))
			{
				PluginDir = ProjectPlugins / TEXT("UnrealEngineAIAssist");
			}
			else
			{
				UE_LOG(LogAIAssist, Warning, TEXT("Could not locate plugin directory, falling back to EnginePluginsDir"));
				PluginDir = SearchDir / TEXT("UnrealEngineAIAssist");
			}
		}
	}

	// Normalize
	FPaths::NormalizeDirectoryName(PluginDir);
	UE_LOG(LogAIAssist, Display, TEXT("UnrealEngineAIAssist: PluginDir = %s"), *PluginDir);
}

void FUnrealEngineAIAssistModule::WritePluginConfig()
{
	FString ConfigPath = PluginDir / TEXT("plugin.config.json");
	FString EngineDir = FPaths::ConvertRelativePathToFull(FPaths::EngineDir());
	FPaths::NormalizeDirectoryName(EngineDir);

	// Detect engine version
	FString EngineVersion = FEngineVersion::Current().ToString();

	// Build JSON
	TSharedPtr<FJsonObject> Config = MakeShared<FJsonObject>();
	Config->SetStringField(TEXT("engine_dir"), EngineDir);
	Config->SetStringField(TEXT("plugin_dir"), PluginDir);
	Config->SetStringField(TEXT("engine_version"), EngineVersion);

	FString Output;
	TSharedRef<TJsonWriter<TCHAR, TPrettyJsonPrintPolicy<TCHAR>>> Writer =
		TJsonWriterFactory<TCHAR, TPrettyJsonPrintPolicy<TCHAR>>::Create(&Output);
	FJsonSerializer::Serialize(Config.ToSharedRef(), Writer);
	Writer->Close();

	FFileHelper::SaveStringToFile(Output, *ConfigPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	UE_LOG(LogAIAssist, Display, TEXT("UnrealEngineAIAssist: Wrote %s"), *ConfigPath);
}

// ============================================================================
// Log capture output device — writes to owner's ring buffer
// ============================================================================

class FUnrealEngineAIAssistModule::FLogCapture : public FOutputDevice
{
public:
	FLogCapture(FUnrealEngineAIAssistModule* InOwner) : Owner(InOwner) {}

	virtual void Serialize(const TCHAR* Message, ELogVerbosity::Type Verbosity,
		const FName& Category) override
	{
		FLogEntry Entry;
		Entry.Category = Category.ToString();
		Entry.Message = Message;
		switch (Verbosity)
		{
		case ELogVerbosity::Error:   Entry.Verbosity = TEXT("error"); break;
		case ELogVerbosity::Warning: Entry.Verbosity = TEXT("warning"); break;
		default:                     Entry.Verbosity = TEXT("info"); break;
		}
		Entry.Timestamp = FPlatformTime::Seconds();

		FScopeLock Lock(&Owner->LogBufferLock);
		if (Owner->LogBuffer.Num() >= MaxLogEntries)
		{
			Owner->LogBuffer.RemoveAt(0);
		}
		Owner->LogBuffer.Add(MoveTemp(Entry));
	}

	FUnrealEngineAIAssistModule* Owner;
};

// ============================================================================
// Module lifecycle
// ============================================================================

void FUnrealEngineAIAssistModule::StartupModule()
{
	// Resolve plugin directory and write config (engine_dir, plugin_dir)
	InitPluginDir();
	WritePluginConfig();

	// Start log capture
	LogCaptureDevice = new FLogCapture(this);
	GLog->AddOutputDevice(LogCaptureDevice);

	// Parse port override from command line
	FString PortStr;
	if (FParse::Value(FCommandLine::Get(), TEXT("-AgentBridgePort="), PortStr))
	{
		Port = (uint16)FCString::Atoi(*PortStr);
	}
	StartServer();
}

void FUnrealEngineAIAssistModule::ShutdownModule()
{
	StopServer();

	if (LogCaptureDevice)
	{
		GLog->RemoveOutputDevice(LogCaptureDevice);
		delete LogCaptureDevice;
		LogCaptureDevice = nullptr;
	}
}

void FUnrealEngineAIAssistModule::StartServer()
{
	if (bIsRunning) return;

	ISocketSubsystem* SocketSub = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	if (!SocketSub) { UE_LOG(LogAIAssist, Error, TEXT("No socket subsystem")); return; }

	TSharedPtr<FSocket> Sock = MakeShareable(
		SocketSub->CreateSocket(NAME_Stream, TEXT("AgentBridgeListener"), false));
	if (!Sock.IsValid()) { UE_LOG(LogAIAssist, Error, TEXT("Failed to create socket")); return; }

	Sock->SetReuseAddr(true);
	Sock->SetNonBlocking(true);

	FIPv4Address Addr; FIPv4Address::Parse(TEXT("127.0.0.1"), Addr);
	FIPv4Endpoint Endpoint(Addr, Port);

	if (!Sock->Bind(*Endpoint.ToInternetAddr()))
	{
		UE_LOG(LogAIAssist, Error, TEXT("Bind failed on 127.0.0.1:%d"), Port);
		return;
	}
	if (!Sock->Listen(5))
	{
		UE_LOG(LogAIAssist, Error, TEXT("Listen failed")); return;
	}

	ListenerSocket = Sock;
	bIsRunning = true;
	UE_LOG(LogAIAssist, Display, TEXT("UnrealEngineAIAssist: Listening on 127.0.0.1:%d"), Port);

	Runnable = new FBridgeRunnable(this, ListenerSocket);
	ServerThread = FRunnableThread::Create(Runnable, TEXT("AgentBridgeThread"), 0, TPri_Normal);
}

void FUnrealEngineAIAssistModule::StopServer()
{
	if (!bIsRunning) return;
	bIsRunning = false;

	if (Runnable) { Runnable->Stop(); }
	if (ServerThread) { ServerThread->Kill(true); delete ServerThread; ServerThread = nullptr; }
	delete Runnable; Runnable = nullptr;

	if (ListenerSocket.IsValid())
	{
		ListenerSocket->Close();
		ListenerSocket.Reset();
	}
	UE_LOG(LogAIAssist, Display, TEXT("UnrealEngineAIAssist: Server stopped"));
}

// ============================================================================
// TCP thread (FBridgeRunnable)
// ============================================================================

FUnrealEngineAIAssistModule::FBridgeRunnable::FBridgeRunnable(
	FUnrealEngineAIAssistModule* InOwner, TSharedPtr<FSocket> InListener)
	: Owner(InOwner), ListenerSocket(InListener), bRunning(true)
{}

FUnrealEngineAIAssistModule::FBridgeRunnable::~FBridgeRunnable() {}

bool FUnrealEngineAIAssistModule::FBridgeRunnable::Init() { return true; }
void FUnrealEngineAIAssistModule::FBridgeRunnable::Exit() {}
void FUnrealEngineAIAssistModule::FBridgeRunnable::Stop() { bRunning = false; }

uint32 FUnrealEngineAIAssistModule::FBridgeRunnable::Run()
{
	while (bRunning)
	{
		bool bPending = false;
		if (ListenerSocket->HasPendingConnection(bPending) && bPending)
		{
			FSocket* Client = ListenerSocket->Accept(TEXT("AgentBridgeClient"));
			if (Client)
			{
				HandleClient(Client);
				ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Client);
			}
		}
		FPlatformProcess::Sleep(0.01f);
	}
	return 0;
}

void FUnrealEngineAIAssistModule::FBridgeRunnable::HandleClient(FSocket* Client)
{
	Client->SetNonBlocking(false);

	TArray<uint8> RecvBuffer;
	uint8 Chunk[65536];

	// Read until we get a newline
	while (bRunning)
	{
		int32 BytesRead = 0;
		if (Client->Recv(Chunk, sizeof(Chunk), BytesRead))
		{
			if (BytesRead > 0)
			{
				RecvBuffer.Append(Chunk, BytesRead);

				// Check for newline delimiter
				int32 NewlineIdx = INDEX_NONE;
				for (int32 i = 0; i < RecvBuffer.Num(); ++i)
				{
					if (RecvBuffer[i] == '\n') { NewlineIdx = i; break; }
				}

				if (NewlineIdx != INDEX_NONE)
				{
					FString Message = FString(NewlineIdx, UTF8_TO_TCHAR((const char*)RecvBuffer.GetData()));
					ProcessMessage(Client, Message);
					return;
				}
			}
		}
		else
		{
			break; // Connection closed or error
		}
	}
}

void FUnrealEngineAIAssistModule::FBridgeRunnable::ProcessMessage(
	FSocket* Client, const FString& Message)
{
	auto SendError = [Client](const FString& Err)
	{
		FString ErrResponse = FString::Printf(
			TEXT("{\"success\":false,\"error\":\"%s\"}\n"), *Err);
		FTCHARToUTF8 UTF8Resp(*ErrResponse);
		int32 BytesSent = 0;
		Client->Send((const uint8*)UTF8Resp.Get(), UTF8Resp.Length(), BytesSent);
	};

	TSharedPtr<FJsonObject> JsonMsg;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Message);
	if (!FJsonSerializer::Deserialize(Reader, JsonMsg) || !JsonMsg.IsValid())
	{
		UE_LOG(LogAIAssist, Warning, TEXT("Invalid JSON received: %s"), *Message);
		SendError(TEXT("Invalid JSON"));
		return;
	}

	FString Command;
	if (!JsonMsg->TryGetStringField(TEXT("command"), Command))
	{
		UE_LOG(LogAIAssist, Warning, TEXT("Missing 'command' field"));
		SendError(TEXT("Missing command field"));
		return;
	}

	TSharedPtr<FJsonObject> Params = MakeShareable(new FJsonObject());
	if (JsonMsg->HasField(TEXT("params")))
	{
		auto ParamsVal = JsonMsg->TryGetField(TEXT("params"));
		if (ParamsVal.IsValid() && ParamsVal->Type == EJson::Object)
		{
			Params = ParamsVal->AsObject();
		}
	}

	// Dispatch on GameThread and wait
	FString Response = Owner->DispatchCommand(Command, Params);
	Response += TEXT("\n");

	FTCHARToUTF8 UTF8Resp(*Response);
	const uint8* Data = (const uint8*)UTF8Resp.Get();
	int32 Total = UTF8Resp.Length();
	int32 Sent = 0;

	while (Sent < Total)
	{
		int32 BytesSent = 0;
		if (!Client->Send(Data + Sent, Total - Sent, BytesSent))
		{
			UE_LOG(LogAIAssist, Error, TEXT("Send failed after %d/%d bytes"), Sent, Total);
			return;
		}
		Sent += BytesSent;
	}
}

// ============================================================================
// GameThread dispatch
// ============================================================================

FString FUnrealEngineAIAssistModule::DispatchCommand(
	const FString& Command, const TSharedPtr<FJsonObject>& Params)
{
	TPromise<FString> Promise;
	TFuture<FString> Future = Promise.GetFuture();

	AsyncTask(ENamedThreads::GameThread,
		[this, Command, Params, Promise = MoveTemp(Promise)]() mutable
	{
		TSharedPtr<FJsonObject> Result;

		if (Command == TEXT("ping"))
		{
			Result = HandlePing(Params);
		}
		else if (Command == TEXT("exec_python"))
		{
			Result = HandleExecPython(Params);
		}
		else if (Command == TEXT("describe_object"))
		{
			Result = HandleDescribeObject(Params);
		}
		else if (Command == TEXT("generate_catalog"))
		{
			Result = HandleGenerateCatalog(Params);
		}
		else if (Command == TEXT("get_log"))
		{
			Result = HandleGetLog(Params);
		}
		else if (Command == TEXT("reflect"))
		{
			Result = HandleReflect(Params);
		}
		else
		{
			Result = MakeShared<FJsonObject>();
			Result->SetBoolField(TEXT("success"), false);
			Result->SetStringField(TEXT("error"),
				FString::Printf(TEXT("Unknown command: %s"), *Command));
		}

		FString Out;
		TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
		FJsonSerializer::Serialize(Result.ToSharedRef(), W);
		W->Close();
		// Strip newlines/tabs so the response is a single line (protocol delimiter is \n)
		Out.ReplaceInline(TEXT("\r\n"), TEXT(""));
		Out.ReplaceInline(TEXT("\n"), TEXT(""));
		Out.ReplaceInline(TEXT("\t"), TEXT(""));
		Promise.SetValue(Out);
	});

	return Future.Get();
}

// ============================================================================
// ping
// ============================================================================

TSharedPtr<FJsonObject> FUnrealEngineAIAssistModule::HandlePing(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();
	R->SetBoolField(TEXT("success"), true);
	R->SetStringField(TEXT("message"), TEXT("pong"));
	return R;
}

// ============================================================================
// exec_python
// ============================================================================

TSharedPtr<FJsonObject> FUnrealEngineAIAssistModule::HandleExecPython(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

#if HAS_PYTHON_SCRIPT_PLUGIN
	if (!Params->HasField(TEXT("code")))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing required parameter: code"));
		return R;
	}

	FString Code = Params->GetStringField(TEXT("code"));
	if (Code.IsEmpty())
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Parameter 'code' cannot be empty"));
		return R;
	}

	IPythonScriptPlugin* Py = IPythonScriptPlugin::Get();
	if (!Py || !Py->IsPythonAvailable())
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("PythonScriptPlugin not available"));
		return R;
	}

	FPythonCommandEx Cmd;
	Cmd.Command = Code;
	Cmd.ExecutionMode = EPythonCommandExecutionMode::ExecuteFile;
	Cmd.FileExecutionScope = EPythonFileExecutionScope::Public;
	Cmd.Flags = EPythonCommandFlags::Unattended;

	// Auto-detect: single expression → EvaluateStatement for return value
	bool bSingleExpr = !Code.Contains(TEXT("\n")) && !Code.Contains(TEXT(";")) &&
		!Code.StartsWith(TEXT("import ")) && !Code.StartsWith(TEXT("from ")) &&
		!Code.StartsWith(TEXT("def ")) && !Code.StartsWith(TEXT("class ")) &&
		!Code.StartsWith(TEXT("for ")) && !Code.StartsWith(TEXT("while ")) &&
		!Code.StartsWith(TEXT("if ")) && !Code.StartsWith(TEXT("with ")) &&
		!Code.StartsWith(TEXT("try:"));

	if (bSingleExpr)
	{
		Cmd.ExecutionMode = EPythonCommandExecutionMode::EvaluateStatement;
	}

	bool bSuccess = Py->ExecPythonCommandEx(Cmd);

	R->SetBoolField(TEXT("success"), bSuccess);
	R->SetStringField(TEXT("result"), Cmd.CommandResult);

	TArray<TSharedPtr<FJsonValue>> LogArr;
	for (const FPythonLogOutputEntry& Entry : Cmd.LogOutput)
	{
		auto E = MakeShared<FJsonObject>();
		FString TypeStr;
		switch (Entry.Type)
		{
		case EPythonLogOutputType::Info:    TypeStr = TEXT("info"); break;
		case EPythonLogOutputType::Warning: TypeStr = TEXT("warning"); break;
		case EPythonLogOutputType::Error:   TypeStr = TEXT("error"); break;
		default: TypeStr = TEXT("info"); break;
		}
		E->SetStringField(TEXT("type"), TypeStr);
		E->SetStringField(TEXT("output"), Entry.Output);
		LogArr.Add(MakeShared<FJsonValueObject>(E));
	}
	R->SetArrayField(TEXT("log_output"), LogArr);
#else
	R->SetBoolField(TEXT("success"), false);
	R->SetStringField(TEXT("error"), TEXT("PythonScriptPlugin not compiled in"));
#endif

	return R;
}

// ============================================================================
// describe_object
// ============================================================================

TSharedPtr<FJsonObject> FUnrealEngineAIAssistModule::HandleDescribeObject(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	if (!Params->HasField(TEXT("object_path")))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing required parameter: object_path"));
		return R;
	}

	FString ObjectPath = Params->GetStringField(TEXT("object_path"));
	UClass* TargetClass = FindClassByNameOrPath(ObjectPath);

	if (!TargetClass)
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"),
			FString::Printf(TEXT("Could not find class or object: %s"), *ObjectPath));
		return R;
	}

	R->SetBoolField(TEXT("success"), true);
	R->SetStringField(TEXT("class_name"), TargetClass->GetName());
	R->SetStringField(TEXT("python_class"),
		FString::Printf(TEXT("unreal.%s"), *TargetClass->GetName()));

	if (TargetClass->GetSuperClass())
	{
		R->SetStringField(TEXT("parent_class"), TargetClass->GetSuperClass()->GetName());
	}

	// Functions
	TArray<TSharedPtr<FJsonValue>> Funcs;
	for (TFieldIterator<UFunction> It(TargetClass); It; ++It)
	{
		UFunction* Func = *It;
		if (!Func->HasAnyFunctionFlags(FUNC_BlueprintCallable | FUNC_BlueprintEvent | FUNC_BlueprintPure))
			continue;

		auto FJ = MakeShared<FJsonObject>();
		FJ->SetStringField(TEXT("name"), Func->GetName());
		FJ->SetStringField(TEXT("python_name"), PythonizeName(Func->GetName()));
		FJ->SetBoolField(TEXT("is_static"), Func->HasAnyFunctionFlags(FUNC_Static));
		FJ->SetBoolField(TEXT("is_pure"), Func->HasAnyFunctionFlags(FUNC_BlueprintPure));

		if (Func->GetOwnerClass())
			FJ->SetStringField(TEXT("defined_in"), Func->GetOwnerClass()->GetName());
		if (Func->HasMetaData(TEXT("ToolTip")))
			FJ->SetStringField(TEXT("description"), Func->GetMetaData(TEXT("ToolTip")));

		// Parameters
		TArray<TSharedPtr<FJsonValue>> ParamArr;
		FProperty* RetProp = nullptr;
		for (TFieldIterator<FProperty> PropIt(Func); PropIt; ++PropIt)
		{
			FProperty* P = *PropIt;
			if (P->HasAnyPropertyFlags(CPF_ReturnParm)) { RetProp = P; continue; }
			if (!P->HasAnyPropertyFlags(CPF_Parm)) continue;

			auto PJ = MakeShared<FJsonObject>();
			PJ->SetStringField(TEXT("name"), PythonizeName(P->GetName()));
			PJ->SetStringField(TEXT("type"), P->GetCPPType());
			PJ->SetStringField(TEXT("python_type"), GetPythonType(P));
			ParamArr.Add(MakeShared<FJsonValueObject>(PJ));
		}
		FJ->SetArrayField(TEXT("params"), ParamArr);
		FJ->SetStringField(TEXT("return_type"), RetProp ? RetProp->GetCPPType() : TEXT("void"));

		Funcs.Add(MakeShared<FJsonValueObject>(FJ));
	}
	R->SetArrayField(TEXT("functions"), Funcs);
	R->SetNumberField(TEXT("function_count"), Funcs.Num());

	// Properties
	TArray<TSharedPtr<FJsonValue>> Props;
	for (TFieldIterator<FProperty> It(TargetClass); It; ++It)
	{
		FProperty* P = *It;
		if (!P->HasAnyPropertyFlags(CPF_BlueprintVisible)) continue;

		auto PJ = MakeShared<FJsonObject>();
		PJ->SetStringField(TEXT("name"), P->GetName());
		PJ->SetStringField(TEXT("type"), P->GetCPPType());
		PJ->SetBoolField(TEXT("read_only"), P->HasAnyPropertyFlags(CPF_BlueprintReadOnly));
		Props.Add(MakeShared<FJsonValueObject>(PJ));
	}
	R->SetArrayField(TEXT("properties"), Props);
	R->SetNumberField(TEXT("property_count"), Props.Num());

	return R;
}

// ============================================================================
// generate_catalog
// ============================================================================

TSharedPtr<FJsonObject> FUnrealEngineAIAssistModule::HandleGenerateCatalog(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	FString OutputDir;
	if (Params->HasField(TEXT("output_dir")))
	{
		OutputDir = Params->GetStringField(TEXT("output_dir"));
	}
	if (OutputDir.IsEmpty())
	{
		OutputDir = PluginDir / GetAgentDirName() / TEXT("knowledge") / TEXT("callable_catalog");
	}
	OutputDir = FPaths::ConvertRelativePathToFull(OutputDir);

	FString ClassesDir = OutputDir / TEXT("classes");
	IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
	if (!PF.DirectoryExists(*OutputDir))  PF.CreateDirectoryTree(*OutputDir);
	if (!PF.DirectoryExists(*ClassesDir)) PF.CreateDirectoryTree(*ClassesDir);

	struct FClassEntry
	{
		FString ClassName, ModuleName, Category, Description;
		int32 FuncCount;
		bool bEditorOnly;
	};
	TArray<FClassEntry> AllClasses;
	TMap<FString, int32> CatFuncCounts;
	TMap<FString, TArray<FString>> CatClasses;
	int32 TotalFuncs = 0;

	for (TObjectIterator<UClass> It; It; ++It)
	{
		UClass* C = *It;
		if (ShouldExcludeClass(C)) continue;

		TArray<TSharedPtr<FJsonValue>> FuncArray;
		for (TFieldIterator<UFunction> FI(C, EFieldIteratorFlags::ExcludeSuper); FI; ++FI)
		{
			UFunction* Func = *FI;
			if (!ShouldExportFunction(Func)) continue;

			auto FJ = MakeShared<FJsonObject>();
			FString FName = Func->GetName();
			FJ->SetStringField(TEXT("name"), FName);
			FJ->SetStringField(TEXT("python_name"), PythonizeName(FName));
			FJ->SetStringField(TEXT("safety_level"), ClassifySafety(FName));
			FJ->SetBoolField(TEXT("is_static"), Func->HasAnyFunctionFlags(FUNC_Static));
			FJ->SetBoolField(TEXT("is_pure"), Func->HasAnyFunctionFlags(FUNC_BlueprintPure));

			FString Tip;
			if (Func->HasMetaData(TEXT("ToolTip"))) Tip = Func->GetMetaData(TEXT("ToolTip"));
			FJ->SetStringField(TEXT("description"), Tip);

			// Params
			TArray<TSharedPtr<FJsonValue>> PArr;
			FProperty* RetP = nullptr;
			for (TFieldIterator<FProperty> PropIt(Func); PropIt; ++PropIt)
			{
				FProperty* P = *PropIt;
				if (P->HasAnyPropertyFlags(CPF_ReturnParm)) { RetP = P; continue; }
				if (!P->HasAnyPropertyFlags(CPF_Parm)) continue;

				auto PJ = MakeShared<FJsonObject>();
				PJ->SetStringField(TEXT("name"), PythonizeName(P->GetName()));
				PJ->SetStringField(TEXT("type"), P->GetCPPType());
				PJ->SetStringField(TEXT("python_type"), GetPythonType(P));
				PArr.Add(MakeShared<FJsonValueObject>(PJ));
			}
			FJ->SetArrayField(TEXT("params"), PArr);
			FJ->SetStringField(TEXT("return_type"), RetP ? RetP->GetCPPType() : TEXT("void"));
			FJ->SetStringField(TEXT("python_return_type"), RetP ? GetPythonType(RetP) : TEXT("None"));

			// Python snippet
			FString PyCls = C->GetName();
			FString PyFunc = PythonizeName(FName);
			if (Func->HasAnyFunctionFlags(FUNC_Static))
				FJ->SetStringField(TEXT("python_snippet"),
					FString::Printf(TEXT("unreal.%s.%s(...)"), *PyCls, *PyFunc));
			else
				FJ->SetStringField(TEXT("python_snippet"),
					FString::Printf(TEXT("%s.%s(...)"), *PythonizeName(PyCls), *PyFunc));

			FuncArray.Add(MakeShared<FJsonValueObject>(FJ));
		}

		if (FuncArray.Num() == 0) continue;

		// Module name
		UPackage* Pkg = C->GetOutermost();
		FString ModName = TEXT("Unknown");
		if (Pkg)
		{
			FString PkgName = Pkg->GetName();
			int32 Idx;
			if (PkgName.FindLastChar(TEXT('/'), Idx)) ModName = PkgName.Mid(Idx + 1);
			else ModName = PkgName;
		}

		bool bEditor = C->IsEditorOnly() ||
			ModName.Contains(TEXT("Editor")) || ModName.Contains(TEXT("UnrealEd"));

		FString ClassTip;
		if (C->HasMetaData(TEXT("ToolTip"))) ClassTip = C->GetMetaData(TEXT("ToolTip"));

		// Write per-class JSON
		auto CJ = MakeShared<FJsonObject>();
		CJ->SetStringField(TEXT("class_name"), C->GetName());
		CJ->SetStringField(TEXT("python_class"), FString::Printf(TEXT("unreal.%s"), *C->GetName()));
		CJ->SetStringField(TEXT("module"), ModName);
		CJ->SetBoolField(TEXT("editor_only"), bEditor);
		CJ->SetStringField(TEXT("description"), ClassTip);
		if (C->GetSuperClass())
			CJ->SetStringField(TEXT("parent_class"), C->GetSuperClass()->GetName());
		CJ->SetArrayField(TEXT("functions"), FuncArray);

		FString ClassFile = ClassesDir / (C->GetName() + TEXT(".json"));
		FString ClassOut;
		auto CW = TJsonWriterFactory<TCHAR, TPrettyJsonPrintPolicy<TCHAR>>::Create(&ClassOut);
		FJsonSerializer::Serialize(CJ, *CW);
		CW->Close();
		FFileHelper::SaveStringToFile(ClassOut, *ClassFile, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);

		FString Cat = GetCategoryForModule(ModName);
		FClassEntry Entry;
		Entry.ClassName = C->GetName();
		Entry.ModuleName = ModName;
		Entry.Category = Cat;
		Entry.Description = ClassTip;
		Entry.FuncCount = FuncArray.Num();
		Entry.bEditorOnly = bEditor;
		AllClasses.Add(Entry);

		TotalFuncs += FuncArray.Num();
		CatFuncCounts.FindOrAdd(Cat) += FuncArray.Num();
		CatClasses.FindOrAdd(Cat).Add(C->GetName());
	}

	// catalog_index.json
	{
		auto Idx = MakeShared<FJsonObject>();

		auto Meta = MakeShared<FJsonObject>();
		Meta->SetStringField(TEXT("engine_version"), TEXT("4.26"));
		Meta->SetStringField(TEXT("generated_at"), FDateTime::UtcNow().ToIso8601());
		Meta->SetNumberField(TEXT("total_classes"), AllClasses.Num());
		Meta->SetNumberField(TEXT("total_functions"), TotalFuncs);
		Idx->SetObjectField(TEXT("metadata"), Meta);

		auto Cats = MakeShared<FJsonObject>();
		for (auto& Pair : CatClasses)
		{
			auto CatJ = MakeShared<FJsonObject>();
			CatJ->SetStringField(TEXT("description"), GetCategoryDescription(Pair.Key));
			TArray<TSharedPtr<FJsonValue>> Names;
			for (auto& N : Pair.Value) Names.Add(MakeShared<FJsonValueString>(N));
			CatJ->SetArrayField(TEXT("classes"), Names);
			CatJ->SetNumberField(TEXT("function_count"), CatFuncCounts[Pair.Key]);
			Cats->SetObjectField(Pair.Key, CatJ);
		}
		Idx->SetObjectField(TEXT("categories"), Cats);

		auto ClsIdx = MakeShared<FJsonObject>();
		for (auto& E : AllClasses)
		{
			auto EJ = MakeShared<FJsonObject>();
			EJ->SetStringField(TEXT("module"), E.ModuleName);
			EJ->SetStringField(TEXT("category"), E.Category);
			EJ->SetNumberField(TEXT("function_count"), E.FuncCount);
			EJ->SetBoolField(TEXT("editor_only"), E.bEditorOnly);
			ClsIdx->SetObjectField(E.ClassName, EJ);
		}
		Idx->SetObjectField(TEXT("classes"), ClsIdx);

		FString IdxOut;
		auto IW = TJsonWriterFactory<TCHAR, TPrettyJsonPrintPolicy<TCHAR>>::Create(&IdxOut);
		FJsonSerializer::Serialize(Idx, *IW);
		IW->Close();
		FFileHelper::SaveStringToFile(IdxOut,
			*(OutputDir / TEXT("catalog_index.json")),
			FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	}

	UE_LOG(LogAIAssist, Display, TEXT("Catalog: %d classes, %d functions → %s"),
		AllClasses.Num(), TotalFuncs, *OutputDir);

	R->SetBoolField(TEXT("success"), true);
	R->SetStringField(TEXT("output_dir"), OutputDir);
	R->SetNumberField(TEXT("total_classes"), AllClasses.Num());
	R->SetNumberField(TEXT("total_functions"), TotalFuncs);
	R->SetStringField(TEXT("message"),
		FString::Printf(TEXT("Catalog generated: %d classes, %d functions"), AllClasses.Num(), TotalFuncs));
	return R;
}

// ============================================================================
// get_log
// ============================================================================

TSharedPtr<FJsonObject> FUnrealEngineAIAssistModule::HandleGetLog(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	int32 Count = 50; // default
	if (Params->HasField(TEXT("count")))
	{
		Count = (int32)Params->GetNumberField(TEXT("count"));
	}
	Count = FMath::Clamp(Count, 1, MaxLogEntries);

	FString CategoryFilter;
	if (Params->HasField(TEXT("category")))
	{
		CategoryFilter = Params->GetStringField(TEXT("category"));
	}

	FString VerbosityFilter;
	if (Params->HasField(TEXT("verbosity")))
	{
		VerbosityFilter = Params->GetStringField(TEXT("verbosity"));
	}

	FString TextFilter;
	if (Params->HasField(TEXT("filter")))
	{
		TextFilter = Params->GetStringField(TEXT("filter"));
	}

	TArray<TSharedPtr<FJsonValue>> Entries;
	{
		FScopeLock Lock(&LogBufferLock);
		// Walk backwards to get most recent first, then reverse
		for (int32 i = LogBuffer.Num() - 1; i >= 0 && Entries.Num() < Count; --i)
		{
			const FLogEntry& E = LogBuffer[i];

			if (!CategoryFilter.IsEmpty() && !E.Category.Contains(CategoryFilter))
				continue;
			if (!VerbosityFilter.IsEmpty() && E.Verbosity != VerbosityFilter)
				continue;
			if (!TextFilter.IsEmpty() && !E.Message.Contains(TextFilter))
				continue;

			auto EJ = MakeShared<FJsonObject>();
			EJ->SetStringField(TEXT("category"), E.Category);
			EJ->SetStringField(TEXT("verbosity"), E.Verbosity);
			EJ->SetStringField(TEXT("message"), E.Message);
			EJ->SetNumberField(TEXT("timestamp"), E.Timestamp);
			Entries.Add(MakeShared<FJsonValueObject>(EJ));
		}
	}

	// Reverse so oldest is first
	Algo::Reverse(Entries);

	R->SetBoolField(TEXT("success"), true);
	R->SetNumberField(TEXT("count"), Entries.Num());
	R->SetArrayField(TEXT("entries"), Entries);
	return R;
}

// ============================================================================
// reflect — raw property access via ImportText/ExportTextItem
// ============================================================================

UObject* FUnrealEngineAIAssistModule::ResolveObjectPath(const FString& Path)
{
	// Try exact path first (handles full paths like /Game/UI/WBP.WBP:WidgetTree)
	UObject* Obj = StaticFindObject(UObject::StaticClass(), nullptr, *Path);
	if (Obj) return Obj;
	// Fallback: search in any loaded package
	Obj = FindObjectByNameOrPath(Path);
	return Obj;
}

FUnrealEngineAIAssistModule::FResolvedProperty FUnrealEngineAIAssistModule::ResolvePropertyChain(
	UObject* Root, const FString& PropertyPath)
{
	FResolvedProperty Result;
	if (!Root)
	{
		Result.ErrorMessage = TEXT("Root object is null");
		return Result;
	}

	TArray<FString> Segments;
	PropertyPath.ParseIntoArray(Segments, TEXT("."), true);
	if (Segments.Num() == 0)
	{
		Result.ErrorMessage = TEXT("Property path is empty");
		return Result;
	}

	UObject* Current = Root;

	// Walk intermediate segments (all but last must be object properties)
	for (int32 i = 0; i < Segments.Num() - 1; ++i)
	{
		UClass* Class = Current->GetClass();
		FProperty* Prop = Class->FindPropertyByName(FName(*Segments[i]));
		if (!Prop)
		{
			Result.ErrorMessage = FString::Printf(
				TEXT("Property '%s' not found on %s (%s)"),
				*Segments[i], *Current->GetName(), *Class->GetName());
			return Result;
		}

		FObjectProperty* ObjProp = CastField<FObjectProperty>(Prop);
		if (!ObjProp)
		{
			Result.ErrorMessage = FString::Printf(
				TEXT("Intermediate property '%s' is not an object property (type: %s)"),
				*Segments[i], *Prop->GetCPPType());
			return Result;
		}

		void* ValueAddr = Prop->ContainerPtrToValuePtr<void>(Current);
		UObject* Next = ObjProp->GetObjectPropertyValue(ValueAddr);
		if (!Next)
		{
			Result.ErrorMessage = FString::Printf(
				TEXT("Intermediate property '%s' is null on %s"),
				*Segments[i], *Current->GetName());
			return Result;
		}
		Current = Next;
	}

	// Resolve final segment
	const FString& FinalName = Segments.Last();
	UClass* FinalClass = Current->GetClass();
	FProperty* FinalProp = FinalClass->FindPropertyByName(FName(*FinalName));
	if (!FinalProp)
	{
		Result.ErrorMessage = FString::Printf(
			TEXT("Property '%s' not found on %s (%s)"),
			*FinalName, *Current->GetName(), *FinalClass->GetName());
		return Result;
	}

	Result.Container = Current;
	Result.Property = FinalProp;
	Result.ValuePtr = FinalProp->ContainerPtrToValuePtr<void>(Current);
	return Result;
}

TSharedPtr<FJsonObject> FUnrealEngineAIAssistModule::HandleReflect(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	FString Action;
	if (!Params->TryGetStringField(TEXT("action"), Action))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing required parameter: action (get|set|describe)"));
		return R;
	}

	if (Action == TEXT("get"))         return HandleReflectGet(Params);
	if (Action == TEXT("set"))         return HandleReflectSet(Params);
	if (Action == TEXT("describe"))    return HandleReflectDescribe(Params);

	R->SetBoolField(TEXT("success"), false);
	R->SetStringField(TEXT("error"),
		FString::Printf(TEXT("Unknown reflect action: %s (expected get|set|describe)"), *Action));
	return R;
}

TSharedPtr<FJsonObject> FUnrealEngineAIAssistModule::HandleReflectGet(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	FString ObjectPath;
	if (!Params->TryGetStringField(TEXT("object"), ObjectPath))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing required parameter: object"));
		return R;
	}
	FString PropertyPath;
	if (!Params->TryGetStringField(TEXT("property"), PropertyPath))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing required parameter: property"));
		return R;
	}

	UObject* Root = ResolveObjectPath(ObjectPath);
	if (!Root)
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"),
			FString::Printf(TEXT("Object not found: %s"), *ObjectPath));
		return R;
	}

	FResolvedProperty Resolved = ResolvePropertyChain(Root, PropertyPath);
	if (!Resolved.Property)
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), Resolved.ErrorMessage);
		return R;
	}

	// ExportTextItem_Direct — reads value as text, no permission checks
	FString ValueStr;
	Resolved.Property->ExportTextItem_Direct(ValueStr, Resolved.ValuePtr, nullptr, Resolved.Container, PPF_None);

	R->SetBoolField(TEXT("success"), true);
	R->SetStringField(TEXT("value"), ValueStr);
	R->SetStringField(TEXT("type"), Resolved.Property->GetCPPType());
	R->SetStringField(TEXT("property_name"), Resolved.Property->GetName());
	return R;
}

TSharedPtr<FJsonObject> FUnrealEngineAIAssistModule::HandleReflectSet(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	FString ObjectPath;
	if (!Params->TryGetStringField(TEXT("object"), ObjectPath))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing required parameter: object"));
		return R;
	}
	FString PropertyPath;
	if (!Params->TryGetStringField(TEXT("property"), PropertyPath))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing required parameter: property"));
		return R;
	}
	FString NewValue;
	if (!Params->TryGetStringField(TEXT("value"), NewValue))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing required parameter: value"));
		return R;
	}

	UObject* Root = ResolveObjectPath(ObjectPath);
	if (!Root)
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"),
			FString::Printf(TEXT("Object not found: %s"), *ObjectPath));
		return R;
	}

	FResolvedProperty Resolved = ResolvePropertyChain(Root, PropertyPath);
	if (!Resolved.Property)
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), Resolved.ErrorMessage);
		return R;
	}

	// Record previous value
	FString PreviousValue;
	Resolved.Property->ExportTextItem_Direct(PreviousValue, Resolved.ValuePtr, nullptr, Resolved.Container, PPF_None);

	// ImportText_Direct — writes value, no permission checks
	const TCHAR* ImportResult = Resolved.Property->ImportText_Direct(
		*NewValue, Resolved.ValuePtr, Resolved.Container, PPF_None);

	if (!ImportResult)
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"),
			FString::Printf(TEXT("ImportText failed for property '%s' with value '%s'"),
				*Resolved.Property->GetName(), *NewValue));
		R->SetStringField(TEXT("previous_value"), PreviousValue);
		return R;
	}

	// Notify editor of property change
	FPropertyChangedEvent ChangedEvent(Resolved.Property);
	Resolved.Container->PostEditChangeProperty(ChangedEvent);

	// Read back actual value
	FString ActualValue;
	Resolved.Property->ExportTextItem_Direct(ActualValue, Resolved.ValuePtr, nullptr, Resolved.Container, PPF_None);

	R->SetBoolField(TEXT("success"), true);
	R->SetStringField(TEXT("previous_value"), PreviousValue);
	R->SetStringField(TEXT("new_value"), ActualValue);
	R->SetStringField(TEXT("type"), Resolved.Property->GetCPPType());
	R->SetStringField(TEXT("warning"),
		TEXT("UNSAFE: Bypassed property permission gates via ImportText. Use with caution."));
	return R;
}

TSharedPtr<FJsonObject> FUnrealEngineAIAssistModule::HandleReflectDescribe(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	// Accept both "class" and "class_name" for convenience
	FString ClassName;
	if (!Params->TryGetStringField(TEXT("class"), ClassName))
	{
		Params->TryGetStringField(TEXT("class_name"), ClassName);
	}
	if (ClassName.IsEmpty())
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing required parameter: class or class_name"));
		return R;
	}

	// Resolve class (same logic as describe_object)
	UClass* TargetClass = FindClassByNameOrPath(ClassName);
	if (!TargetClass)
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"),
			FString::Printf(TEXT("Could not find class: %s"), *ClassName));
		return R;
	}

	// Build full JSON data (to be dumped to file)
	auto FullData = MakeShared<FJsonObject>();
	FullData->SetStringField(TEXT("class_name"), TargetClass->GetName());
	if (TargetClass->GetSuperClass())
		FullData->SetStringField(TEXT("parent_class"), TargetClass->GetSuperClass()->GetName());

	// --- Properties: ALL properties, no BlueprintVisible filter ---
	TArray<TSharedPtr<FJsonValue>> PropArray;
	TArray<FString> ReflectOnlyProps;
	int32 PythonAccessible = 0;
	int32 ReflectOnly = 0;

	for (TFieldIterator<FProperty> It(TargetClass); It; ++It)
	{
		FProperty* P = *It;
		auto PJ = MakeShared<FJsonObject>();
		PJ->SetStringField(TEXT("name"), P->GetName());
		PJ->SetStringField(TEXT("type"), P->GetCPPType());
		PJ->SetStringField(TEXT("python_type"), GetPythonType(P));

		if (P->GetOwnerClass())
			PJ->SetStringField(TEXT("defined_in"), P->GetOwnerClass()->GetName());

		// Determine accessibility
		bool bBPVisible = P->HasAnyPropertyFlags(CPF_BlueprintVisible | CPF_Edit);
		bool bBPReadOnly = P->HasAnyPropertyFlags(CPF_BlueprintReadOnly);
		bool bEditConst = P->HasAnyPropertyFlags(CPF_EditConst);

		FString Access;
		if (bBPVisible && !bBPReadOnly && !bEditConst)
		{
			Access = TEXT("python");
			PythonAccessible++;
		}
		else if (bBPVisible && (bBPReadOnly || bEditConst))
		{
			Access = TEXT("python_read_only+reflect_write");
			ReflectOnly++;
			ReflectOnlyProps.Add(P->GetName());
		}
		else
		{
			Access = TEXT("reflect");
			ReflectOnly++;
			ReflectOnlyProps.Add(P->GetName());
		}
		PJ->SetStringField(TEXT("accessible_via"), Access);

		// Property flags summary
		TArray<FString> Flags;
		if (P->HasAnyPropertyFlags(CPF_BlueprintVisible)) Flags.Add(TEXT("BlueprintVisible"));
		if (P->HasAnyPropertyFlags(CPF_BlueprintReadOnly)) Flags.Add(TEXT("BlueprintReadOnly"));
		if (P->HasAnyPropertyFlags(CPF_Edit)) Flags.Add(TEXT("Edit"));
		if (P->HasAnyPropertyFlags(CPF_EditConst)) Flags.Add(TEXT("EditConst"));
		if (P->HasAnyPropertyFlags(CPF_DisableEditOnInstance)) Flags.Add(TEXT("DisableEditOnInstance"));
		if (P->HasAnyPropertyFlags(CPF_DisableEditOnTemplate)) Flags.Add(TEXT("DisableEditOnTemplate"));
		if (P->HasAnyPropertyFlags(CPF_InstancedReference)) Flags.Add(TEXT("Instanced"));
		if (P->HasAnyPropertyFlags(CPF_Transient)) Flags.Add(TEXT("Transient"));
		PJ->SetStringField(TEXT("flags"), FString::Join(Flags, TEXT(", ")));

		if (P->HasMetaData(TEXT("ToolTip")))
			PJ->SetStringField(TEXT("description"), P->GetMetaData(TEXT("ToolTip")));

		PropArray.Add(MakeShared<FJsonValueObject>(PJ));
	}
	FullData->SetArrayField(TEXT("properties"), PropArray);
	FullData->SetNumberField(TEXT("total_properties"), PropArray.Num());
	FullData->SetNumberField(TEXT("python_accessible_properties"), PythonAccessible);
	FullData->SetNumberField(TEXT("reflect_only_properties"), ReflectOnly);

	// --- Functions: ALL functions, no BlueprintCallable filter ---
	TArray<TSharedPtr<FJsonValue>> FuncArray;
	int32 PythonCallable = 0;
	int32 CallMethodOnly = 0;

	for (TFieldIterator<UFunction> It(TargetClass); It; ++It)
	{
		UFunction* Func = *It;
		auto FJ = MakeShared<FJsonObject>();
		FJ->SetStringField(TEXT("name"), Func->GetName());
		FJ->SetStringField(TEXT("python_name"), PythonizeName(Func->GetName()));
		FJ->SetBoolField(TEXT("is_static"), Func->HasAnyFunctionFlags(FUNC_Static));

		if (Func->GetOwnerClass())
			FJ->SetStringField(TEXT("defined_in"), Func->GetOwnerClass()->GetName());
		if (Func->HasMetaData(TEXT("ToolTip")))
			FJ->SetStringField(TEXT("description"), Func->GetMetaData(TEXT("ToolTip")));

		// Determine accessibility
		bool bCallable = Func->HasAnyFunctionFlags(FUNC_BlueprintCallable | FUNC_BlueprintEvent | FUNC_BlueprintPure);
		bool bScript = Func->HasMetaData(TEXT("ScriptMethod")) || Func->HasMetaData(TEXT("ScriptOperator"));
		if (bCallable || bScript)
		{
			FJ->SetStringField(TEXT("accessible_via"), TEXT("python"));
			PythonCallable++;
		}
		else
		{
			FJ->SetStringField(TEXT("accessible_via"), TEXT("python_call_method"));
			CallMethodOnly++;
		}

		// Parameters
		TArray<TSharedPtr<FJsonValue>> ParamArr;
		FProperty* RetProp = nullptr;
		for (TFieldIterator<FProperty> PropIt(Func); PropIt; ++PropIt)
		{
			FProperty* P = *PropIt;
			if (P->HasAnyPropertyFlags(CPF_ReturnParm)) { RetProp = P; continue; }
			if (!P->HasAnyPropertyFlags(CPF_Parm)) continue;

			auto PJ = MakeShared<FJsonObject>();
			PJ->SetStringField(TEXT("name"), PythonizeName(P->GetName()));
			PJ->SetStringField(TEXT("type"), P->GetCPPType());
			ParamArr.Add(MakeShared<FJsonValueObject>(PJ));
		}
		FJ->SetArrayField(TEXT("params"), ParamArr);
		FJ->SetStringField(TEXT("return_type"), RetProp ? RetProp->GetCPPType() : TEXT("void"));

		FuncArray.Add(MakeShared<FJsonValueObject>(FJ));
	}
	FullData->SetArrayField(TEXT("functions"), FuncArray);
	FullData->SetNumberField(TEXT("total_functions"), FuncArray.Num());
	FullData->SetNumberField(TEXT("python_callable_functions"), PythonCallable);
	FullData->SetNumberField(TEXT("call_method_only_functions"), CallMethodOnly);

	// Dump to file
	FString OutputDir = PluginDir / GetAgentDirName() / TEXT("knowledge") / TEXT("mcp_output");
	OutputDir = FPaths::ConvertRelativePathToFull(OutputDir);
	IPlatformFile& PF = FPlatformFileManager::Get().GetPlatformFile();
	if (!PF.DirectoryExists(*OutputDir)) PF.CreateDirectoryTree(*OutputDir);

	FString FilePath = OutputDir / FString::Printf(TEXT("reflect_describe_%s.json"), *TargetClass->GetName());
	FString FileOut;
	auto Writer = TJsonWriterFactory<TCHAR, TPrettyJsonPrintPolicy<TCHAR>>::Create(&FileOut);
	FJsonSerializer::Serialize(FullData, *Writer);
	Writer->Close();
	FFileHelper::SaveStringToFile(FileOut, *FilePath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);

	// Return compact summary
	R->SetBoolField(TEXT("success"), true);
	R->SetStringField(TEXT("class_name"), TargetClass->GetName());
	if (TargetClass->GetSuperClass())
		R->SetStringField(TEXT("parent_class"), TargetClass->GetSuperClass()->GetName());
	R->SetNumberField(TEXT("total_properties"), PropArray.Num());
	R->SetNumberField(TEXT("python_accessible_properties"), PythonAccessible);
	R->SetNumberField(TEXT("reflect_only_properties"), ReflectOnly);
	R->SetNumberField(TEXT("total_functions"), FuncArray.Num());
	R->SetNumberField(TEXT("python_callable_functions"), PythonCallable);
	R->SetNumberField(TEXT("call_method_only_functions"), CallMethodOnly);

	// Include reflect-only property names inline for quick reference
	TArray<TSharedPtr<FJsonValue>> ReflectOnlyArr;
	for (const FString& Name : ReflectOnlyProps)
		ReflectOnlyArr.Add(MakeShared<FJsonValueString>(Name));
	R->SetArrayField(TEXT("reflect_only_property_names"), ReflectOnlyArr);

	R->SetStringField(TEXT("file_path"), FilePath);
	R->SetStringField(TEXT("hint"),
		FString::Printf(TEXT("Full data at: %s — Use Grep to search for specific properties/functions"), *FilePath));

	return R;
}

// ============================================================================
// Catalog helpers
// ============================================================================

FString FUnrealEngineAIAssistModule::PythonizeName(const FString& InName)
{
	FString Name = InName;
	// Strip leading 'b' for booleans (bIsVisible -> is_visible)
	if (Name.Len() > 1 && Name[0] == TEXT('b') && FChar::IsUpper(Name[1]))
	{
		Name = Name.Mid(1);
	}

	FString Result;
	Result.Reserve(Name.Len() + 10);

	for (int32 i = 0; i < Name.Len(); ++i)
	{
		const TCHAR Ch = Name[i];
		if (FChar::IsUpper(Ch))
		{
			if (Result.Len() > 0 && Result[Result.Len() - 1] != TEXT('_'))
			{
				bool bPrevLower = (i > 0) && (FChar::IsLower(Name[i - 1]) || FChar::IsDigit(Name[i - 1]));
				bool bNextLower = (i + 1 < Name.Len()) && FChar::IsLower(Name[i + 1]);
				if (bPrevLower || (bNextLower && i > 0))
				{
					Result += TEXT('_');
				}
			}
			Result += FChar::ToLower(Ch);
		}
		else
		{
			Result += Ch;
		}
	}

	// Handle Python reserved words
	if (Result == TEXT("class")) return TEXT("class_");
	if (Result == TEXT("import")) return TEXT("import_");
	if (Result == TEXT("from")) return TEXT("from_");
	if (Result == TEXT("type")) return TEXT("type_");
	if (Result == TEXT("object")) return TEXT("object_");
	if (Result == TEXT("lambda")) return TEXT("lambda_");

	return Result;
}

FString FUnrealEngineAIAssistModule::ClassifySafety(const FString& FunctionName)
{
	// Read-only prefixes
	static const TCHAR* ReadOnly[] = {
		TEXT("Get"), TEXT("Find"), TEXT("Is"), TEXT("Has"), TEXT("Does"), TEXT("Can"),
		TEXT("Contains"), TEXT("Was"), TEXT("Are"), TEXT("Num"), TEXT("Count"),
		TEXT("Check"), TEXT("Query"), TEXT("Lookup"), TEXT("Search"), TEXT("List"), nullptr
	};
	for (const TCHAR** P = ReadOnly; *P; ++P)
	{
		if (FunctionName.StartsWith(*P)) return TEXT("read_only");
	}

	// Destructive prefixes
	static const TCHAR* Destructive[] = {
		TEXT("Delete"), TEXT("Destroy"), TEXT("Remove"), TEXT("Clear"),
		TEXT("Reset"), TEXT("Purge"), TEXT("Unregister"), nullptr
	};
	for (const TCHAR** P = Destructive; *P; ++P)
	{
		if (FunctionName.StartsWith(*P)) return TEXT("destructive");
	}

	return TEXT("editor_modify");
}

FString FUnrealEngineAIAssistModule::GetCategoryForModule(const FString& ModuleName)
{
	if (ModuleName == TEXT("Engine") || ModuleName == TEXT("GameplayStatics") ||
		ModuleName == TEXT("GameFramework") || ModuleName == TEXT("AIModule"))
		return TEXT("actor_management");
	if (ModuleName == TEXT("AssetRegistry") || ModuleName == TEXT("EditorScriptingUtilities") ||
		ModuleName == TEXT("AssetTools") || ModuleName == TEXT("ContentBrowser"))
		return TEXT("asset_management");
	if (ModuleName == TEXT("UnrealEd") || ModuleName == TEXT("LevelEditor") ||
		ModuleName == TEXT("WorldBrowser"))
		return TEXT("level_management");
	if (ModuleName == TEXT("Renderer") || ModuleName == TEXT("RenderCore") ||
		ModuleName == TEXT("MaterialShaderQualitySettings"))
		return TEXT("rendering");
	if (ModuleName == TEXT("BlueprintGraph") || ModuleName == TEXT("Kismet") ||
		ModuleName == TEXT("BlueprintEditorLibrary"))
		return TEXT("blueprint_editing");
	if (ModuleName == TEXT("StaticMeshEditor") || ModuleName == TEXT("MeshDescription") ||
		ModuleName == TEXT("ProceduralMeshComponent"))
		return TEXT("mesh_geometry");
	if (ModuleName == TEXT("AnimGraph") || ModuleName == TEXT("AnimationCore") ||
		ModuleName == TEXT("Persona"))
		return TEXT("animation");
	if (ModuleName == TEXT("PhysicsCore") || ModuleName == TEXT("PhysXCooking") ||
		ModuleName == TEXT("Chaos"))
		return TEXT("physics");
	if (ModuleName == TEXT("UMG") || ModuleName == TEXT("Slate") ||
		ModuleName == TEXT("SlateCore") || ModuleName == TEXT("UMGEditor"))
		return TEXT("ui_umg");
	return TEXT("general");
}

FString FUnrealEngineAIAssistModule::GetCategoryDescription(const FString& Cat)
{
	if (Cat == TEXT("actor_management"))  return TEXT("Actor spawning, deletion, transform, gameplay");
	if (Cat == TEXT("asset_management"))  return TEXT("Asset loading, saving, importing, registry");
	if (Cat == TEXT("level_management"))  return TEXT("Level loading, streaming, world composition");
	if (Cat == TEXT("rendering"))         return TEXT("Rendering pipeline, materials, shaders, VFX");
	if (Cat == TEXT("blueprint_editing")) return TEXT("Blueprint creation, compilation, node graph");
	if (Cat == TEXT("mesh_geometry"))     return TEXT("Static mesh, skeletal mesh, procedural mesh");
	if (Cat == TEXT("animation"))         return TEXT("Animation sequences, montages, blend spaces");
	if (Cat == TEXT("physics"))           return TEXT("Physics simulation, collision, constraints");
	if (Cat == TEXT("ui_umg"))            return TEXT("UMG widgets, Slate UI, HUD");
	return TEXT("General engine operations");
}

FString FUnrealEngineAIAssistModule::GetPythonType(FProperty* Property)
{
	if (!Property) return TEXT("None");
	if (Property->IsA<FBoolProperty>()) return TEXT("bool");
	if (Property->IsA<FIntProperty>() || Property->IsA<FInt64Property>() ||
		Property->IsA<FByteProperty>() || Property->IsA<FUInt32Property>()) return TEXT("int");
	if (Property->IsA<FFloatProperty>() || Property->IsA<FDoubleProperty>()) return TEXT("float");
	if (Property->IsA<FStrProperty>() || Property->IsA<FNameProperty>() ||
		Property->IsA<FTextProperty>()) return TEXT("str");
	if (FStructProperty* SP = CastField<FStructProperty>(Property))
	{
		FString SN = SP->Struct->GetName();
		if (SN == TEXT("Vector")) return TEXT("unreal.Vector");
		if (SN == TEXT("Rotator")) return TEXT("unreal.Rotator");
		if (SN == TEXT("Transform")) return TEXT("unreal.Transform");
		if (SN == TEXT("LinearColor") || SN == TEXT("Color")) return TEXT("unreal.LinearColor");
		return FString::Printf(TEXT("unreal.%s"), *SN);
	}
	if (FObjectProperty* OP = CastField<FObjectProperty>(Property))
		return FString::Printf(TEXT("unreal.%s"), *OP->PropertyClass->GetName());
	if (FArrayProperty* AP = CastField<FArrayProperty>(Property))
		return FString::Printf(TEXT("unreal.Array[%s]"), *GetPythonType(AP->Inner));
	if (FEnumProperty* EP = CastField<FEnumProperty>(Property))
	{
		if (EP->GetEnum()) return FString::Printf(TEXT("unreal.%s"), *EP->GetEnum()->GetName());
	}
	return TEXT("object");
}

bool FUnrealEngineAIAssistModule::ShouldExcludeClass(UClass* Class)
{
	if (!Class) return true;
	FString N = Class->GetName();
	if (N.Contains(TEXT("SKEL_")) || N.Contains(TEXT("REINST_")) ||
		N.Contains(TEXT("TRASHCLASS_")) || N.Contains(TEXT("PLACEHOLDER_")) ||
		N.Contains(TEXT("HOTRELOADED_")) || N.Contains(TEXT("DEAD_")) ||
		N.Contains(TEXT("Default__")))
		return true;
	if (Class->HasAnyClassFlags(CLASS_Deprecated | CLASS_NewerVersionExists))
		return true;
	return false;
}

bool FUnrealEngineAIAssistModule::ShouldExportFunction(UFunction* Function)
{
	if (!Function) return false;
	bool bCallable = Function->HasAnyFunctionFlags(FUNC_BlueprintCallable | FUNC_BlueprintEvent);
	bool bScript = Function->HasMetaData(TEXT("ScriptMethod")) || Function->HasMetaData(TEXT("ScriptOperator"));
	if (!bCallable && !bScript) return false;
	if (Function->HasMetaData(TEXT("BlueprintInternalUseOnly")))
	{
		const FString& V = Function->GetMetaData(TEXT("BlueprintInternalUseOnly"));
		if (V == TEXT("true") || V == TEXT("True")) return false;
	}
	if (Function->HasMetaData(TEXT("DeprecatedFunction"))) return false;
	return true;
}

// ============================================================================
// Module registration
// ============================================================================

IMPLEMENT_MODULE(FUnrealEngineAIAssistModule, UnrealEngineAIAssist)
