// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class UnrealEngineAIAssist : ModuleRules
{
	public UnrealEngineAIAssist(ReadOnlyTargetRules Target) : base(Target)
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

		// PythonScriptPlugin — conditional module dependency (soft).
		// This is an Editor-only plugin so Python is always present when the user
		// has PythonScriptPlugin enabled.  Use EngineDirectory (available since
		// UE 4.23) to locate the module regardless of whether it lives under
		// Plugins/Experimental/ (UE4/early UE5) or Plugins/Editor/ (UE5.1+).
		{
			string EnginePluginsDir = System.IO.Path.Combine(EngineDirectory, "Plugins");
			string[] PythonSearchPaths = new string[]
			{
				System.IO.Path.Combine(EnginePluginsDir, "Experimental", "PythonScriptPlugin", "Source", "PythonScriptPlugin"),
				System.IO.Path.Combine(EnginePluginsDir, "Editor",       "PythonScriptPlugin", "Source", "PythonScriptPlugin"),
			};
			bool bHasPython = false;
			foreach (string p in PythonSearchPaths)
			{
				if (System.IO.Directory.Exists(p)) { bHasPython = true; break; }
			}
			if (bHasPython)
			{
				PrivateDependencyModuleNames.Add("PythonScriptPlugin");
				PrivateDefinitions.Add("HAS_PYTHON_SCRIPT_PLUGIN=1");
			}
			else
			{
				PrivateDefinitions.Add("HAS_PYTHON_SCRIPT_PLUGIN=0");
			}
		}

		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"Engine",
				"Networking",
				"Projects",
				"Sockets",
				"Json",
				"JsonUtilities"
			}
		);

		// BlueprintEdGraphUtils: expose BP graph editing (nodes, pins, compile) to Python/MCP.
		// These are editor-only modules, safe to depend on since this is an editor plugin.
		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				"UnrealEd",
				"BlueprintGraph",
				"KismetCompiler"
			}
		);
	}
}
