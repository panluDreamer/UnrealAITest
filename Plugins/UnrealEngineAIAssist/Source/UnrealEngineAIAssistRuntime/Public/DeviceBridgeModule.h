// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleInterface.h"
#include "HAL/Runnable.h"

class FJsonObject;
class FSocket;

/**
 * UnrealEngineAIAssistRuntime — TCP client that connects to a host-side
 * devbridge server, receives commands, and executes them via GEngine->Exec().
 *
 * Modeled after Unreal Insights -tracehost: the DEVICE initiates the
 * connection to the HOST (because device WiFi IPs are dynamic but the
 * developer's office IP is stable).
 *
 * Trigger:
 *   -AIAssistDeviceBridgeHost=127.0.0.1:8059   (command-line / ue4commandline.txt)
 *   AIAssistDeviceBridge 127.0.0.1:8059        (console command at runtime)
 *
 * Protocol: newline-delimited JSON, same as the editor module.
 *   Host sends:   {"command":"exec_console","params":{"command":"stat fps"}}\n
 *   Device sends:  {"success":true,"output":"..."}\n
 *
 * Excluded from Shipping builds (DeveloperTool module type).
 */
class FDeviceBridgeModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

private:
#if !DEVICE_BRIDGE_DISABLED

	// ---- Connection management ----

	/** Parse -AIAssistDeviceBridgeHost= and connect if present. */
	void TryAutoConnect();

	/** Start the TCP client thread to connect to host_ip:port. */
	void ConnectToHost(const FString& HostAddr, uint16 InPort);

	/** Stop the client thread and close the socket. */
	void Disconnect();

	// ---- TCP client thread ----

	class FBridgeClientRunnable : public FRunnable
	{
	public:
		FBridgeClientRunnable(FDeviceBridgeModule* InOwner,
			const FString& InHost, uint16 InPort);
		virtual ~FBridgeClientRunnable();

		virtual bool Init() override;
		virtual uint32 Run() override;
		virtual void Stop() override;
		virtual void Exit() override;

	private:
		/** Try to establish TCP connection. Returns socket or nullptr. */
		FSocket* AttemptConnect();

		/** Send the initial handshake JSON. */
		void SendHandshake(FSocket* Sock);

		/** Read one newline-delimited JSON message from socket. Returns false on disconnect. */
		bool ReadMessage(FSocket* Sock, FString& OutMessage);

		/** Send a response string (must end with \n). */
		bool SendResponse(FSocket* Sock, const FString& Response);

		/** Process an incoming command and return the JSON response. */
		FString ProcessCommand(const FString& Message);

		FDeviceBridgeModule* Owner;
		FString HostAddress;
		uint16 Port;
		FThreadSafeBool bRunning;
	};

	// ---- Command handlers (called on GameThread via dispatch) ----

	FString DispatchCommand(const FString& Command, const TSharedPtr<FJsonObject>& Params);

	TSharedPtr<FJsonObject> HandlePing(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleExecConsole(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleExecUnLua(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleGetCVar(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleSetCVar(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleGetLog(const TSharedPtr<FJsonObject>& Params);
	TSharedPtr<FJsonObject> HandleGetInfo(const TSharedPtr<FJsonObject>& Params);

	// ---- Log capture ring buffer ----

	struct FLogEntry
	{
		FString Category;
		FString Message;
		FString Verbosity;
		double Timestamp;
	};

	FCriticalSection LogBufferLock;
	TArray<FLogEntry> LogBuffer;
	static const int32 MaxLogEntries = 1000;

	class FLogCapture;
	FLogCapture* LogCaptureDevice = nullptr;

	// ---- Console commands ----

	TUniquePtr<class FAutoConsoleCommand> BridgeConsoleCommand;
	TUniquePtr<class FAutoConsoleCommand> DisconnectConsoleCommand;

	// ---- State ----

	FBridgeClientRunnable* ClientRunnable = nullptr;
	FRunnableThread* ClientThread = nullptr;
	bool bIsConnected = false;
	uint16 DefaultPort = 8059;

#endif // !DEVICE_BRIDGE_DISABLED
};
