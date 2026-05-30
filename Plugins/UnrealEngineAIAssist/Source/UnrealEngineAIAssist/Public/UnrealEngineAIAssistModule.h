// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleInterface.h"
#include "HAL/Runnable.h"
#include "Sockets.h"

// Forward declarations — avoid pulling in Json.h / UObject headers from the module header
class FJsonObject;
class FProperty;
class UClass;
class UFunction;

/**
 * UnrealEngineAIAssist — lightweight TCP server for AI agent ↔ UE Editor interaction.
 *
 * Listens on 127.0.0.1:13090 (configurable via -AgentBridgePort=).
 * Protocol: newline-delimited JSON.
 *   Request:  {"command":"X","params":{...}}\n
 *   Response: {"success":true,...}\n
 *
 * Three commands:
 *   exec_python     — run Python code in the editor (IPythonScriptPlugin)
 *   describe_object — UHT reflection introspection for a UClass
 *   generate_catalog— scan all UClasses and emit a JSON callable catalog
 *   get_log         — retrieve recent editor log lines (optionally filtered by category)
 */
class FUnrealEngineAIAssistModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

private:
	void StartServer();
	void StopServer();

	/** TCP listener thread */
	class FBridgeRunnable : public FRunnable
	{
	public:
		FBridgeRunnable(FUnrealEngineAIAssistModule* InOwner, TSharedPtr<FSocket> InListener);
		virtual ~FBridgeRunnable();

		virtual bool Init() override;
		virtual uint32 Run() override;
		virtual void Stop() override;
		virtual void Exit() override;

	private:
		void HandleClient(FSocket* Client);
		void ProcessMessage(FSocket* Client, const FString& Message);

		FUnrealEngineAIAssistModule* Owner;
		TSharedPtr<FSocket> ListenerSocket;
		bool bRunning;
	};

	/** Dispatch command on GameThread, block TCP thread until result ready. */
	FString DispatchCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params);

	// Command handlers (called on GameThread)
	TSharedPtr<FJsonObject> HandlePing(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleExecPython(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleDescribeObject(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleGenerateCatalog(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleGetLog(const TSharedPtr<FJsonObject>& Params);

	// reflect command — raw property access via ImportText/ExportTextItem (bypasses permission gates)
	struct FResolvedProperty
	{
		UObject* Container = nullptr;
		FProperty* Property = nullptr;
		void* ValuePtr = nullptr;
		FString ErrorMessage;
	};

	TSharedPtr<FJsonObject> HandleReflect(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleReflectGet(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleReflectSet(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleReflectDescribe(const TSharedPtr<FJsonObject>& Params);

	static UObject* ResolveObjectPath(const FString& Path);
	static FResolvedProperty ResolvePropertyChain(UObject* Root, const FString& PropertyPath);

	// Log capture ring buffer
	struct FLogEntry
	{
		FString Category;
		FString Message;
		FString Verbosity;
		double Timestamp;
	};
	FCriticalSection LogBufferLock;
	TArray<FLogEntry> LogBuffer;
	static const int32 MaxLogEntries = 500;
	class FLogCapture;
	FLogCapture* LogCaptureDevice = nullptr;

	// Catalog generation helpers (static, called on GameThread)
	static FString PythonizeName(const FString& InName);
	static FString ClassifySafety(const FString& FunctionName);
	static FString GetCategoryForModule(const FString& ModuleName);
	static FString GetCategoryDescription(const FString& Category);
	static FString GetPythonType(FProperty* Property);
	static bool ShouldExcludeClass(UClass* Class);
	static bool ShouldExportFunction(UFunction* Function);

	/** Resolve and cache the plugin root directory (where .uplugin lives). */
	void InitPluginDir();

	/** Write plugin.config.json to PluginDir with engine_dir, plugin_dir, engine_version. */
	void WritePluginConfig();

	TSharedPtr<FSocket> ListenerSocket;
	FRunnableThread* ServerThread = nullptr;
	FBridgeRunnable* Runnable = nullptr;
	uint16 Port = 13090;
	bool bIsRunning = false;

	/** Absolute path to the plugin root directory (e.g. .../Plugins/UnrealEngineAIAssist/). */
	FString PluginDir;
};
