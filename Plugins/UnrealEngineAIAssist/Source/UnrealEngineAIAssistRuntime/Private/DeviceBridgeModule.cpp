// Copyright Epic Games, Inc. All Rights Reserved.

#include "DeviceBridgeModule.h"
#include "Modules/ModuleManager.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "IPAddressAsyncResolve.h"
#include "HAL/RunnableThread.h"
#include "Misc/StringOutputDevice.h"
#include "Interfaces/IPv4/IPv4Address.h"
#include "Interfaces/IPv4/IPv4Endpoint.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonWriter.h"
#include "Async/Async.h"
#include "Misc/EngineVersion.h"
#include "HAL/IConsoleManager.h"
#include "Engine/GameInstance.h"

DEFINE_LOG_CATEGORY_STATIC(LogDeviceBridge, Log, All);

IMPLEMENT_MODULE(FDeviceBridgeModule, UnrealEngineAIAssistRuntime)

#if !DEVICE_BRIDGE_DISABLED

// ============================================================================
// JSON helpers
// ============================================================================

static FString JsonToString(const TSharedPtr<FJsonObject>& Obj)
{
	FString Out;
	TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> W =
		TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
	FJsonSerializer::Serialize(Obj.ToSharedRef(), W);
	W->Close();
	Out.ReplaceInline(TEXT("\r\n"), TEXT(""));
	Out.ReplaceInline(TEXT("\n"), TEXT(""));
	Out.ReplaceInline(TEXT("\t"), TEXT(""));
	return Out;
}

// ============================================================================
// Log capture (same pattern as editor module)
// ============================================================================

class FDeviceBridgeModule::FLogCapture : public FOutputDevice
{
public:
	FLogCapture(FDeviceBridgeModule* InOwner) : Owner(InOwner) {}

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

	FDeviceBridgeModule* Owner;
};

// ============================================================================
// Module lifecycle
// ============================================================================

void FDeviceBridgeModule::StartupModule()
{
	// Start log capture
	LogCaptureDevice = new FLogCapture(this);
	GLog->AddOutputDevice(LogCaptureDevice);

	// Register console command: AIAssistDeviceBridge <host_ip>[:<port>]
	BridgeConsoleCommand = MakeUnique<FAutoConsoleCommand>(
		TEXT("AIAssistDeviceBridge"),
		TEXT("Connect to devbridge host server. Usage: AIAssistDeviceBridge <host_ip>[:<port>]"),
		FConsoleCommandWithArgsDelegate::CreateLambda(
			[this](const TArray<FString>& Args)
			{
				if (Args.Num() < 1)
				{
					UE_LOG(LogDeviceBridge, Warning,
						TEXT("Usage: AIAssistDeviceBridge <host_ip>[:<port>]"));
					return;
				}

				FString HostArg = Args[0];
				FString Host;
				uint16 Port = DefaultPort;

				// Parse host:port
				int32 ColonIdx;
				if (HostArg.FindChar(TEXT(':'), ColonIdx))
				{
					Host = HostArg.Left(ColonIdx);
					Port = (uint16)FCString::Atoi(*HostArg.Mid(ColonIdx + 1));
				}
				else
				{
					Host = HostArg;
				}

				ConnectToHost(Host, Port);
			}
		)
	);

	// Register console command: AIAssistDeviceBridgeDisconnect
	DisconnectConsoleCommand = MakeUnique<FAutoConsoleCommand>(
		TEXT("AIAssistDeviceBridgeDisconnect"),
		TEXT("Disconnect from devbridge host server."),
		FConsoleCommandDelegate::CreateLambda(
			[this]()
			{
				if (bIsConnected)
				{
					Disconnect();
					UE_LOG(LogDeviceBridge, Display, TEXT("DeviceBridge: Disconnected by console command."));
				}
				else
				{
					UE_LOG(LogDeviceBridge, Display, TEXT("DeviceBridge: Not connected."));
				}
			}
		)
	);

	UE_LOG(LogDeviceBridge, Display,
		TEXT("DeviceBridge: Module loaded. Use 'AIAssistDeviceBridge <host_ip>:<port>' to connect."));

	// Check for auto-connect via command line
	TryAutoConnect();
}

void FDeviceBridgeModule::ShutdownModule()
{
	Disconnect();

	BridgeConsoleCommand.Reset();
	DisconnectConsoleCommand.Reset();

	if (LogCaptureDevice)
	{
		GLog->RemoveOutputDevice(LogCaptureDevice);
		delete LogCaptureDevice;
		LogCaptureDevice = nullptr;
	}
}

void FDeviceBridgeModule::TryAutoConnect()
{
	FString HostStr;
	if (FParse::Value(FCommandLine::Get(), TEXT("-AIAssistDeviceBridgeHost="), HostStr))
	{
		FString Host;
		uint16 Port = DefaultPort;

		int32 ColonIdx;
		if (HostStr.FindChar(TEXT(':'), ColonIdx))
		{
			Host = HostStr.Left(ColonIdx);
			Port = (uint16)FCString::Atoi(*HostStr.Mid(ColonIdx + 1));
		}
		else
		{
			Host = HostStr;
		}

		UE_LOG(LogDeviceBridge, Display,
			TEXT("DeviceBridge: Auto-connecting to %s:%d (from command line)"), *Host, Port);
		ConnectToHost(Host, Port);
	}
}

void FDeviceBridgeModule::ConnectToHost(const FString& HostAddr, uint16 InPort)
{
	// Disconnect existing if any
	Disconnect();

	UE_LOG(LogDeviceBridge, Display,
		TEXT("DeviceBridge: Connecting to %s:%d ..."), *HostAddr, InPort);

	ClientRunnable = new FBridgeClientRunnable(this, HostAddr, InPort);
	ClientThread = FRunnableThread::Create(
		ClientRunnable, TEXT("DeviceBridgeClient"), 0, TPri_Normal);
	bIsConnected = true;
}

void FDeviceBridgeModule::Disconnect()
{
	if (!bIsConnected) return;
	bIsConnected = false;

	if (ClientRunnable) { ClientRunnable->Stop(); }
	if (ClientThread)
	{
		ClientThread->Kill(true);
		delete ClientThread;
		ClientThread = nullptr;
	}
	delete ClientRunnable;
	ClientRunnable = nullptr;

	UE_LOG(LogDeviceBridge, Display, TEXT("DeviceBridge: Disconnected"));
}

// ============================================================================
// TCP client thread
// ============================================================================

FDeviceBridgeModule::FBridgeClientRunnable::FBridgeClientRunnable(
	FDeviceBridgeModule* InOwner, const FString& InHost, uint16 InPort)
	: Owner(InOwner), HostAddress(InHost), Port(InPort), bRunning(true)
{}

FDeviceBridgeModule::FBridgeClientRunnable::~FBridgeClientRunnable() {}
bool FDeviceBridgeModule::FBridgeClientRunnable::Init() { return true; }
void FDeviceBridgeModule::FBridgeClientRunnable::Exit() {}
void FDeviceBridgeModule::FBridgeClientRunnable::Stop() { bRunning = false; }

uint32 FDeviceBridgeModule::FBridgeClientRunnable::Run()
{
	while (bRunning)
	{
		// Attempt connection
		FSocket* Sock = AttemptConnect();
		if (!Sock)
		{
			// Retry after 5 seconds
			for (int32 i = 0; i < 50 && bRunning; ++i)
			{
				FPlatformProcess::Sleep(0.1f);
			}
			continue;
		}

		UE_LOG(LogDeviceBridge, Display,
			TEXT("DeviceBridge: Connected to %s:%d"), *HostAddress, Port);

		// Send handshake
		SendHandshake(Sock);

		// Enter command receive loop
		while (bRunning)
		{
			FString Message;
			if (!ReadMessage(Sock, Message))
			{
				UE_LOG(LogDeviceBridge, Warning,
					TEXT("DeviceBridge: Connection lost, will reconnect..."));
				break;
			}

			// Process command and send response
			FString Response = ProcessCommand(Message);
			Response += TEXT("\n");
			if (!SendResponse(Sock, Response))
			{
				UE_LOG(LogDeviceBridge, Warning,
					TEXT("DeviceBridge: Send failed, will reconnect..."));
				break;
			}
		}

		// Clean up socket
		Sock->Close();
		ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Sock);

		// Brief pause before reconnect
		if (bRunning)
		{
			FPlatformProcess::Sleep(2.0f);
		}
	}
	return 0;
}

FSocket* FDeviceBridgeModule::FBridgeClientRunnable::AttemptConnect()
{
	ISocketSubsystem* SocketSub = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	if (!SocketSub) return nullptr;

	FSocket* Sock = SocketSub->CreateSocket(NAME_Stream, TEXT("DeviceBridgeClient"), false);
	if (!Sock) return nullptr;

	FIPv4Address Addr;
	if (!FIPv4Address::Parse(HostAddress, Addr))
	{
		// Try DNS resolve
		auto ResolveInfo = SocketSub->GetHostByName(TCHAR_TO_ANSI(*HostAddress));
		if (ResolveInfo && ResolveInfo->GetErrorCode() == SE_NO_ERROR)
		{
			uint32 IP;
			ResolveInfo->GetResolvedAddress().GetIp(IP);
			Addr = FIPv4Address(IP);
		}
		else
		{
			UE_LOG(LogDeviceBridge, Warning,
				TEXT("DeviceBridge: Cannot resolve host '%s'"), *HostAddress);
			SocketSub->DestroySocket(Sock);
			return nullptr;
		}
	}

	FIPv4Endpoint Endpoint(Addr, Port);

	Sock->SetNonBlocking(false);

	// Connect with timeout
	if (!Sock->Connect(*Endpoint.ToInternetAddr()))
	{
		UE_LOG(LogDeviceBridge, Warning,
			TEXT("DeviceBridge: Connect to %s:%d failed"), *HostAddress, Port);
		SocketSub->DestroySocket(Sock);
		return nullptr;
	}

	return Sock;
}

void FDeviceBridgeModule::FBridgeClientRunnable::SendHandshake(FSocket* Sock)
{
	TSharedPtr<FJsonObject> Info = MakeShared<FJsonObject>();
	Info->SetStringField(TEXT("event"), TEXT("connected"));
	Info->SetStringField(TEXT("module"), TEXT("DeviceBridge"));
	Info->SetStringField(TEXT("version"), TEXT("1.0"));
	Info->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());

	// Platform info
#if PLATFORM_ANDROID
	Info->SetStringField(TEXT("platform"), TEXT("Android"));
#elif PLATFORM_IOS
	Info->SetStringField(TEXT("platform"), TEXT("IOS"));
#elif PLATFORM_WINDOWS
	Info->SetStringField(TEXT("platform"), TEXT("Windows"));
#elif PLATFORM_MAC
	Info->SetStringField(TEXT("platform"), TEXT("Mac"));
#elif PLATFORM_LINUX
	Info->SetStringField(TEXT("platform"), TEXT("Linux"));
#else
	Info->SetStringField(TEXT("platform"), TEXT("Unknown"));
#endif

	FString Msg = JsonToString(Info) + TEXT("\n");
	SendResponse(Sock, Msg);
}

bool FDeviceBridgeModule::FBridgeClientRunnable::ReadMessage(
	FSocket* Sock, FString& OutMessage)
{
	TArray<uint8> RecvBuffer;
	uint8 Chunk[65536];

	while (bRunning)
	{
		int32 BytesRead = 0;
		if (!Sock->Recv(Chunk, sizeof(Chunk), BytesRead))
		{
			return false; // Connection error
		}
		if (BytesRead == 0)
		{
			return false; // Connection closed
		}

		RecvBuffer.Append(Chunk, BytesRead);

		// Check for newline delimiter
		for (int32 i = 0; i < RecvBuffer.Num(); ++i)
		{
			if (RecvBuffer[i] == '\n')
			{
				OutMessage = FString(i, UTF8_TO_TCHAR((const char*)RecvBuffer.GetData()));
				return true;
			}
		}
	}
	return false;
}

bool FDeviceBridgeModule::FBridgeClientRunnable::SendResponse(
	FSocket* Sock, const FString& Response)
{
	FTCHARToUTF8 UTF8Resp(*Response);
	const uint8* Data = (const uint8*)UTF8Resp.Get();
	int32 Total = UTF8Resp.Length();
	int32 Sent = 0;

	while (Sent < Total)
	{
		int32 BytesSent = 0;
		if (!Sock->Send(Data + Sent, Total - Sent, BytesSent))
		{
			return false;
		}
		Sent += BytesSent;
	}
	return true;
}

FString FDeviceBridgeModule::FBridgeClientRunnable::ProcessCommand(const FString& Message)
{
	auto MakeError = [](const FString& Err) -> FString
	{
		auto R = MakeShared<FJsonObject>();
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), Err);
		return JsonToString(R);
	};

	TSharedPtr<FJsonObject> JsonMsg;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Message);
	if (!FJsonSerializer::Deserialize(Reader, JsonMsg) || !JsonMsg.IsValid())
	{
		return MakeError(TEXT("Invalid JSON"));
	}

	FString Command;
	if (!JsonMsg->TryGetStringField(TEXT("command"), Command))
	{
		return MakeError(TEXT("Missing command field"));
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

	return Owner->DispatchCommand(Command, Params);
}

// ============================================================================
// GameThread dispatch (same pattern as editor module)
// ============================================================================

FString FDeviceBridgeModule::DispatchCommand(
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
		else if (Command == TEXT("exec_console"))
		{
			Result = HandleExecConsole(Params);
		}
		else if (Command == TEXT("exec_unlua"))
		{
			Result = HandleExecUnLua(Params);
		}
		else if (Command == TEXT("get_cvar"))
		{
			Result = HandleGetCVar(Params);
		}
		else if (Command == TEXT("set_cvar"))
		{
			Result = HandleSetCVar(Params);
		}
		else if (Command == TEXT("get_log"))
		{
			Result = HandleGetLog(Params);
		}
		else if (Command == TEXT("get_info"))
		{
			Result = HandleGetInfo(Params);
		}
		else
		{
			Result = MakeShared<FJsonObject>();
			Result->SetBoolField(TEXT("success"), false);
			Result->SetStringField(TEXT("error"),
				FString::Printf(TEXT("Unknown command: %s"), *Command));
		}

		Promise.SetValue(JsonToString(Result));
	});

	return Future.Get();
}

// ============================================================================
// Command handlers
// ============================================================================

TSharedPtr<FJsonObject> FDeviceBridgeModule::HandlePing(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();
	R->SetBoolField(TEXT("success"), true);
	R->SetStringField(TEXT("message"), TEXT("pong"));
	return R;
}

TSharedPtr<FJsonObject> FDeviceBridgeModule::HandleExecConsole(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	FString Command;
	if (!Params->TryGetStringField(TEXT("command"), Command))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing 'command' parameter"));
		return R;
	}

	FStringOutputDevice OutputDevice;
	OutputDevice.SetAutoEmitLineTerminator(true);

	UWorld* World = nullptr;
	if (GEngine && GEngine->GetWorldContexts().Num() > 0)
	{
		World = GEngine->GetWorldContexts()[0].World();
	}

	if (World)
	{
		// Try GameInstance first (routes to UFUNCTION(Exec) like ExecDoString)
		bool bHandled = false;
		UGameInstance* GI = World->GetGameInstance();
		if (GI)
		{
			bHandled = GI->ProcessConsoleExec(*Command, OutputDevice, nullptr);
		}
		// Fall back to GEngine->Exec for global console commands (stat, show, etc.)
		if (!bHandled)
		{
			GEngine->Exec(World, *Command, OutputDevice);
		}
		R->SetBoolField(TEXT("success"), true);
		R->SetStringField(TEXT("output"), *OutputDevice);
	}
	else
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("No active World"));
	}

	return R;
}

TSharedPtr<FJsonObject> FDeviceBridgeModule::HandleExecUnLua(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	FString Code;
	if (!Params->TryGetStringField(TEXT("code"), Code))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing 'code' parameter"));
		return R;
	}

	// Route through ExecDoString console command
	FString ConsoleCmd = FString::Printf(TEXT("ExecDoString %s"), *Code);

	UWorld* World = nullptr;
	if (GEngine && GEngine->GetWorldContexts().Num() > 0)
	{
		World = GEngine->GetWorldContexts()[0].World();
	}

	if (!World)
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("No active World"));
		return R;
	}

	UGameInstance* GI = World->GetGameInstance();
	if (!GI)
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("No GameInstance"));
		return R;
	}

	// Route through GameInstance's ProcessConsoleExec — this reaches UFUNCTION(Exec) functions
	FStringOutputDevice OutputDevice;
	OutputDevice.SetAutoEmitLineTerminator(true);
	bool bHandled = GI->ProcessConsoleExec(*ConsoleCmd, OutputDevice, nullptr);

	if (!bHandled)
	{
		// Fallback to GEngine->Exec
		GEngine->Exec(World, *ConsoleCmd, OutputDevice);
	}

	// Search LogBuffer for RetVal — scan from end (most recent) backwards
	// ExecDoString writes "ExecDoString RetVal:xxx" via UE_LOG(LogTemp, Log, ...)
	// Note: LogBuffer is a FIFO with RemoveAt(0) when full, so forward-index
	// from a pre-recorded position is unreliable. Reverse scan is safe.
	FString RetVal;
	FString Error;
	{
		FScopeLock Lock(&LogBufferLock);
		// Search last 20 entries (ExecDoString result should be very recent)
		int32 SearchStart = FMath::Max(0, LogBuffer.Num() - 20);
		for (int32 i = LogBuffer.Num() - 1; i >= SearchStart; --i)
		{
			const FString& Msg = LogBuffer[i].Message;
			// Match "ExecDoString RetVal:xxx" (any prefix before ExecDoString is acceptable)
			int32 RetValIdx = Msg.Find(TEXT("ExecDoString RetVal:"));
			if (RetValIdx != INDEX_NONE)
			{
				RetVal = Msg.Mid(RetValIdx + 20).TrimStartAndEnd();
				break;  // Found the most recent one
			}
			// Match error patterns
			if (Error.IsEmpty() && (Msg.Contains(TEXT("Error:[")) || Msg.Contains(TEXT("Error: ["))))
			{
				Error = Msg;
			}
		}
	}

	// Prefer LogBuffer RetVal, fallback to OutputDevice output
	FString FinalOutput = RetVal.IsEmpty() ? FString(*OutputDevice) : RetVal;

	R->SetBoolField(TEXT("success"), Error.IsEmpty());
	R->SetStringField(TEXT("output"), FinalOutput);
	if (!Error.IsEmpty())
	{
		R->SetStringField(TEXT("error"), Error);
	}

	return R;
}

TSharedPtr<FJsonObject> FDeviceBridgeModule::HandleGetCVar(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	FString Name;
	if (!Params->TryGetStringField(TEXT("name"), Name))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing 'name' parameter"));
		return R;
	}

	IConsoleVariable* CVar = IConsoleManager::Get().FindConsoleVariable(*Name);
	if (CVar)
	{
		R->SetBoolField(TEXT("success"), true);
		R->SetStringField(TEXT("name"), Name);
		R->SetStringField(TEXT("value"), CVar->GetString());
	}
	else
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"),
			FString::Printf(TEXT("CVar '%s' not found"), *Name));
	}
	return R;
}

TSharedPtr<FJsonObject> FDeviceBridgeModule::HandleSetCVar(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	FString Name, Value;
	if (!Params->TryGetStringField(TEXT("name"), Name) ||
		!Params->TryGetStringField(TEXT("value"), Value))
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"), TEXT("Missing 'name' or 'value' parameter"));
		return R;
	}

	IConsoleVariable* CVar = IConsoleManager::Get().FindConsoleVariable(*Name);
	if (CVar)
	{
		FString Previous = CVar->GetString();
		CVar->Set(*Value, ECVF_SetByConsole);
		R->SetBoolField(TEXT("success"), true);
		R->SetStringField(TEXT("name"), Name);
		R->SetStringField(TEXT("previous"), Previous);
		R->SetStringField(TEXT("value"), CVar->GetString());
	}
	else
	{
		R->SetBoolField(TEXT("success"), false);
		R->SetStringField(TEXT("error"),
			FString::Printf(TEXT("CVar '%s' not found"), *Name));
	}
	return R;
}

TSharedPtr<FJsonObject> FDeviceBridgeModule::HandleGetLog(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();

	int32 Count = 100;
	if (Params->HasField(TEXT("count")))
	{
		Count = (int32)Params->GetNumberField(TEXT("count"));
	}
	Count = FMath::Clamp(Count, 1, MaxLogEntries);

	FString CategoryFilter, VerbosityFilter, TextFilter;
	Params->TryGetStringField(TEXT("category"), CategoryFilter);
	Params->TryGetStringField(TEXT("verbosity"), VerbosityFilter);
	Params->TryGetStringField(TEXT("filter"), TextFilter);

	TArray<TSharedPtr<FJsonValue>> Entries;

	{
		FScopeLock Lock(&LogBufferLock);
		int32 Start = FMath::Max(0, LogBuffer.Num() - Count);

		for (int32 i = Start; i < LogBuffer.Num(); ++i)
		{
			const FLogEntry& E = LogBuffer[i];

			// Apply filters
			if (!CategoryFilter.IsEmpty() &&
				!E.Category.Contains(CategoryFilter, ESearchCase::IgnoreCase))
			{
				continue;
			}
			if (!VerbosityFilter.IsEmpty() &&
				!E.Verbosity.Equals(VerbosityFilter, ESearchCase::IgnoreCase))
			{
				continue;
			}
			if (!TextFilter.IsEmpty() &&
				!E.Message.Contains(TextFilter, ESearchCase::IgnoreCase))
			{
				continue;
			}

			auto Entry = MakeShared<FJsonObject>();
			Entry->SetStringField(TEXT("category"), E.Category);
			Entry->SetStringField(TEXT("message"), E.Message);
			Entry->SetStringField(TEXT("verbosity"), E.Verbosity);
			Entry->SetNumberField(TEXT("timestamp"), E.Timestamp);
			Entries.Add(MakeShared<FJsonValueObject>(Entry));
		}
	}

	R->SetBoolField(TEXT("success"), true);
	R->SetArrayField(TEXT("entries"), Entries);
	return R;
}

TSharedPtr<FJsonObject> FDeviceBridgeModule::HandleGetInfo(
	const TSharedPtr<FJsonObject>& Params)
{
	auto R = MakeShared<FJsonObject>();
	R->SetBoolField(TEXT("success"), true);
	R->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());

#if PLATFORM_ANDROID
	R->SetStringField(TEXT("platform"), TEXT("Android"));
#elif PLATFORM_IOS
	R->SetStringField(TEXT("platform"), TEXT("IOS"));
#elif PLATFORM_WINDOWS
	R->SetStringField(TEXT("platform"), TEXT("Windows"));
#elif PLATFORM_MAC
	R->SetStringField(TEXT("platform"), TEXT("Mac"));
#elif PLATFORM_LINUX
	R->SetStringField(TEXT("platform"), TEXT("Linux"));
#else
	R->SetStringField(TEXT("platform"), TEXT("Unknown"));
#endif

	// Device name
	R->SetStringField(TEXT("device_name"), FPlatformMisc::GetDefaultDeviceProfileName());
	R->SetStringField(TEXT("cpu_brand"), FPlatformMisc::GetCPUBrand());

	return R;
}

#else // DEVICE_BRIDGE_DISABLED

void FDeviceBridgeModule::StartupModule()
{
	// Shipping build — do nothing
}

void FDeviceBridgeModule::ShutdownModule()
{
	// Shipping build — do nothing
}

#endif // !DEVICE_BRIDGE_DISABLED
