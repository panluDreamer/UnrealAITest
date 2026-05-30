// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class UnrealEngineAIAssistRuntime : ModuleRules
{
	public UnrealEngineAIAssistRuntime(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicIncludePaths.AddRange(
			new string[] {
				System.IO.Path.Combine(ModuleDirectory, "Public")
			}
		);

		PrivateIncludePaths.AddRange(
			new string[] {
				System.IO.Path.Combine(ModuleDirectory, "Private")
			}
		);

		// Runtime-safe dependencies only — NO editor modules
		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"Engine",
				"Networking",
				"Sockets",
				"Json",
				"JsonUtilities"
			}
		);

		// Belt-and-suspenders Shipping guard (module is DeveloperTool so UBT
		// already excludes it from Shipping, but this lets code compile-guard too)
		if (Target.Configuration == UnrealTargetConfiguration.Shipping)
		{
			PrivateDefinitions.Add("DEVICE_BRIDGE_DISABLED=1");
		}
		else
		{
			PrivateDefinitions.Add("DEVICE_BRIDGE_DISABLED=0");
		}
	}
}
