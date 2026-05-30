// Copyright Epic Games, Inc. All Rights Reserved.

#include "BlueprintEdGraphUtils.h"

#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraph/EdGraphSchema.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CallFunction.h"
#include "K2Node_Event.h"
#include "Engine/Blueprint.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet2/BlueprintEditorUtils.h"

// ---- Graph discovery ----

UEdGraph* UBlueprintEdGraphUtils::GetEventGraph(UBlueprint* Blueprint)
{
	if (!Blueprint)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::GetEventGraph: Blueprint is null"));
		return nullptr;
	}
	if (Blueprint->UbergraphPages.Num() == 0)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::GetEventGraph: Blueprint has no UbergraphPages"));
		return nullptr;
	}
	return Blueprint->UbergraphPages[0];
}

TArray<UEdGraph*> UBlueprintEdGraphUtils::GetAllGraphs(UBlueprint* Blueprint)
{
	TArray<UEdGraph*> Result;
	if (!Blueprint)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::GetAllGraphs: Blueprint is null"));
		return Result;
	}
	Result.Append(Blueprint->UbergraphPages);
	Result.Append(Blueprint->FunctionGraphs);
	return Result;
}

// ---- Node operations ----

TArray<UEdGraphNode*> UBlueprintEdGraphUtils::GetGraphNodes(UEdGraph* Graph)
{
	TArray<UEdGraphNode*> Result;
	if (!Graph)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::GetGraphNodes: Graph is null"));
		return Result;
	}
	Result = Graph->Nodes;
	return Result;
}

UEdGraphNode* UBlueprintEdGraphUtils::AddNode(UEdGraph* Graph, TSubclassOf<UEdGraphNode> NodeClass,
                                               int32 PosX, int32 PosY)
{
	if (!Graph || !NodeClass)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::AddNode: Graph or NodeClass is null"));
		return nullptr;
	}

	// Create the node via NewObject and manually initialize it,
	// mirroring what FGraphNodeCreator::Finalize does.
	UEdGraphNode* Node = NewObject<UEdGraphNode>(Graph, NodeClass);
	Node->CreateNewGuid();
	Node->PostPlacedNewNode();
	Node->NodePosX = PosX;
	Node->NodePosY = PosY;
	Node->AllocateDefaultPins();

	// Add to graph (public API)
	Graph->AddNode(Node, /*bUserAction=*/false, /*bSelectNewNode=*/false);
	Graph->NotifyGraphChanged();

	return Node;
}

bool UBlueprintEdGraphUtils::RemoveNode(UEdGraphNode* Node)
{
	if (!Node)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::RemoveNode: Node is null"));
		return false;
	}

	UEdGraph* Graph = Node->GetGraph();
	if (!Graph)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::RemoveNode: Node has no owning graph"));
		return false;
	}

	return Graph->RemoveNode(Node, /*bBreakAllLinks=*/true);
}

// ---- Pin operations ----

TArray<FString> UBlueprintEdGraphUtils::DescribePins(UEdGraphNode* Node)
{
	TArray<FString> Result;
	if (!Node)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::DescribePins: Node is null"));
		return Result;
	}

	for (UEdGraphPin* Pin : Node->Pins)
	{
		if (!Pin)
		{
			continue;
		}
		FString DirStr = (Pin->Direction == EGPD_Input) ? TEXT("In") : TEXT("Out");
		FString Desc = FString::Printf(TEXT("%s:%s:%s"),
			*Pin->GetName(),
			*DirStr,
			*Pin->PinType.PinCategory.ToString());
		Result.Add(Desc);
	}
	return Result;
}

bool UBlueprintEdGraphUtils::ConnectPins(UEdGraphNode* NodeA, const FString& PinNameA,
                                          UEdGraphNode* NodeB, const FString& PinNameB)
{
	if (!NodeA || !NodeB)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::ConnectPins: One or both nodes are null"));
		return false;
	}

	UEdGraphPin* PinA = NodeA->FindPin(FName(*PinNameA));
	UEdGraphPin* PinB = NodeB->FindPin(FName(*PinNameB));

	if (!PinA)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::ConnectPins: Pin '%s' not found on NodeA (%s)"),
			*PinNameA, *NodeA->GetNodeTitle(ENodeTitleType::FullTitle).ToString());
		return false;
	}
	if (!PinB)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::ConnectPins: Pin '%s' not found on NodeB (%s)"),
			*PinNameB, *NodeB->GetNodeTitle(ENodeTitleType::FullTitle).ToString());
		return false;
	}

	// Use schema-aware connection for proper type checking and auto-conversion
	const UEdGraphSchema* Schema = NodeA->GetGraph()->GetSchema();
	if (Schema)
	{
		return Schema->TryCreateConnection(PinA, PinB);
	}

	// Fallback: direct link (no schema validation)
	PinA->MakeLinkTo(PinB);
	return true;
}

bool UBlueprintEdGraphUtils::BreakPinLink(UEdGraphNode* NodeA, const FString& PinNameA,
                                           UEdGraphNode* NodeB, const FString& PinNameB)
{
	if (!NodeA || !NodeB)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::BreakPinLink: One or both nodes are null"));
		return false;
	}

	UEdGraphPin* PinA = NodeA->FindPin(FName(*PinNameA));
	UEdGraphPin* PinB = NodeB->FindPin(FName(*PinNameB));

	if (!PinA || !PinB)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::BreakPinLink: Pin not found"));
		return false;
	}

	PinA->BreakLinkTo(PinB);
	return true;
}

bool UBlueprintEdGraphUtils::BreakAllPinLinks(UEdGraphNode* Node, const FString& PinName)
{
	if (!Node)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::BreakAllPinLinks: Node is null"));
		return false;
	}

	UEdGraphPin* Pin = Node->FindPin(FName(*PinName));
	if (!Pin)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::BreakAllPinLinks: Pin '%s' not found"), *PinName);
		return false;
	}

	Pin->BreakAllPinLinks(/*bNotifyNodes=*/true);
	return true;
}

bool UBlueprintEdGraphUtils::SetPinDefaultValue(UEdGraphNode* Node, const FString& PinName,
                                                  const FString& DefaultValue)
{
	if (!Node)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::SetPinDefaultValue: Node is null"));
		return false;
	}

	UEdGraphPin* Pin = Node->FindPin(FName(*PinName));
	if (!Pin)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::SetPinDefaultValue: Pin '%s' not found"), *PinName);
		return false;
	}

	// Use the schema to set the default value if possible (handles validation)
	const UEdGraphSchema* Schema = Node->GetGraph()->GetSchema();
	if (Schema)
	{
		Schema->TrySetDefaultValue(*Pin, DefaultValue);
	}
	else
	{
		Pin->DefaultValue = DefaultValue;
	}

	Node->PinDefaultValueChanged(Pin);
	return true;
}

// ---- K2Node helpers ----

bool UBlueprintEdGraphUtils::SetCallFunctionTarget(UEdGraphNode* CallFuncNode,
                                                    UClass* FunctionClass, const FString& FunctionName)
{
	if (!CallFuncNode || !FunctionClass)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::SetCallFunctionTarget: Node or Class is null"));
		return false;
	}

	UK2Node_CallFunction* CallNode = Cast<UK2Node_CallFunction>(CallFuncNode);
	if (!CallNode)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::SetCallFunctionTarget: Node is not a K2Node_CallFunction"));
		return false;
	}

	UFunction* Func = FunctionClass->FindFunctionByName(FName(*FunctionName));
	if (!Func)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::SetCallFunctionTarget: Function '%s' not found on class '%s'"),
			*FunctionName, *FunctionClass->GetName());
		return false;
	}

	CallNode->SetFromFunction(Func);
	CallNode->ReconstructNode();
	return true;
}

UEdGraphNode* UBlueprintEdGraphUtils::FindEventNode(UBlueprint* Blueprint, const FString& EventName)
{
	if (!Blueprint)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::FindEventNode: Blueprint is null"));
		return nullptr;
	}

	UEdGraph* EventGraph = GetEventGraph(Blueprint);
	if (!EventGraph)
	{
		return nullptr;
	}

	FName EventFName(*EventName);
	for (UEdGraphNode* Node : EventGraph->Nodes)
	{
		UK2Node_Event* EventNode = Cast<UK2Node_Event>(Node);
		if (EventNode && EventNode->GetFunctionName() == EventFName)
		{
			return EventNode;
		}
	}

	UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::FindEventNode: Event '%s' not found"), *EventName);
	return nullptr;
}

// ---- Compilation ----

bool UBlueprintEdGraphUtils::CompileBlueprint(UBlueprint* Blueprint)
{
	if (!Blueprint)
	{
		UE_LOG(LogTemp, Warning, TEXT("BlueprintEdGraphUtils::CompileBlueprint: Blueprint is null"));
		return false;
	}

	FKismetEditorUtilities::CompileBlueprint(Blueprint);
	return (Blueprint->Status == BS_UpToDate);
}
