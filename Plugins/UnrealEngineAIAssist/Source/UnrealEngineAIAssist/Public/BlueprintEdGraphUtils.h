// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "BlueprintEdGraphUtils.generated.h"

class UEdGraph;
class UEdGraphNode;
class UBlueprint;

/**
 * Static utility library exposing EdGraph pin/node operations as UFUNCTIONs.
 * Enables AI agents to edit Blueprint graphs via exec_python + reflect.
 *
 * Pin and node manipulation APIs (MakeLinkTo, CreatePin, etc.) live outside
 * the UHT reflection system; this wrapper brings them into UFUNCTION scope
 * so they are discoverable and callable through Python scripting.
 *
 * Built into the UnrealEngineAIAssist plugin — no engine patches required.
 */
UCLASS()
class UBlueprintEdGraphUtils : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	// ---- Graph discovery ----

	/** Get the event graph (first UbergraphPage) of a Blueprint. Returns nullptr if none. */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static UEdGraph* GetEventGraph(UBlueprint* Blueprint);

	/** Get all graphs (Ubergraph + Function) of a Blueprint. */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static TArray<UEdGraph*> GetAllGraphs(UBlueprint* Blueprint);

	// ---- Node operations ----

	/** Get all nodes in a graph. */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static TArray<UEdGraphNode*> GetGraphNodes(UEdGraph* Graph);

	/** Add a node of the given class to the graph at (X,Y). Calls AllocateDefaultPins. */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static UEdGraphNode* AddNode(UEdGraph* Graph, TSubclassOf<UEdGraphNode> NodeClass,
	                             int32 PosX = 0, int32 PosY = 0);

	/** Remove a node from its graph. Breaks all links first. */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static bool RemoveNode(UEdGraphNode* Node);

	// ---- Pin operations ----

	/** Get all pin descriptions for a node. Returns array of "PinName:Direction(In/Out):PinCategory". */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static TArray<FString> DescribePins(UEdGraphNode* Node);

	/**
	 * Connect two pins by node + pin name.
	 * Uses the graph schema's TryCreateConnection for proper type validation.
	 * Returns true on success.
	 */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static bool ConnectPins(UEdGraphNode* NodeA, const FString& PinNameA,
	                        UEdGraphNode* NodeB, const FString& PinNameB);

	/** Break the link between two specific pins. */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static bool BreakPinLink(UEdGraphNode* NodeA, const FString& PinNameA,
	                         UEdGraphNode* NodeB, const FString& PinNameB);

	/** Break all links on a specific pin. */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static bool BreakAllPinLinks(UEdGraphNode* Node, const FString& PinName);

	/** Set a pin's default value (for literal inputs). */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static bool SetPinDefaultValue(UEdGraphNode* Node, const FString& PinName,
	                               const FString& DefaultValue);

	// ---- K2Node helpers ----

	/**
	 * Configure a K2Node_CallFunction to call a specific function by class + name.
	 * Reconstructs the node's pins after setting the function reference.
	 */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static bool SetCallFunctionTarget(UEdGraphNode* CallFuncNode,
	                                  UClass* FunctionClass, const FString& FunctionName);

	/** Find an event node by name (e.g. "ReceiveBeginPlay") in a Blueprint's event graph. */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static UEdGraphNode* FindEventNode(UBlueprint* Blueprint, const FString& EventName);

	// ---- Compilation ----

	/** Compile a Blueprint. Returns true if compilation succeeded (status == BS_UpToDate). */
	UFUNCTION(BlueprintCallable, Category="BlueprintEdGraph")
	static bool CompileBlueprint(UBlueprint* Blueprint);
};
