import os
import shutil
import subprocess
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Dict
from pathlib import Path

class OdexPatcherAdvanced:
    """
    An advanced Python class for Odexing and Deodexing Android APK and JAR files.

    This class provides more control and error handling compared to a basic script.
    It leverages multi-threading for potentially faster processing of multiple files.

    Requires the Android SDK's `dex2oat` (for Odexing) and potentially other tools
    to be available in the system's PATH or specified explicitly.
    """

    def __init__(self, android_sdk_path: str = None, num_threads: int = 4, tmp_dir: str = "tmp_odex_patcher"):
        """
        Initializes the OdexPatcherAdvanced.

        Args:
            android_sdk_path: Path to the Android SDK directory. If None, assumes
                              `dex2oat` is in the system's PATH.
            num_threads: Number of threads to use for parallel processing.
            tmp_dir: Directory to use for temporary file operations.
        """
        self.android_sdk_path = android_sdk_path
        self.num_threads = num_threads
        self.tmp_dir = Path(tmp_dir)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.dex2oat_path = self._find_dex2oat()

    def _find_dex2oat(self) -> str:
        """
        Locates the `dex2oat` executable.

        Returns:
            The absolute path to `dex2oat`.

        Raises:
            FileNotFoundError: If `dex2oat` cannot be found.
        """
        if self.android_sdk_path:
            dex2oat_path = Path(self.android_sdk_path) / "art" / "compiler" / "dex2oat"
            if dex2oat_path.is_file() and os.access(dex2oat_path, os.X_OK):
                return str(dex2oat_path)
            else:
                raise FileNotFoundError(
                    f"`dex2oat` not found at expected location: {dex2oat_path}. "
                    "Please ensure the Android SDK path is correct."
                )
        else:
            dex2oat_executable = "dex2oat"
            if shutil.which(dex2oat_executable):
                return dex2oat_executable
            else:
                raise FileNotFoundError(
                    "`dex2oat` not found in system's PATH. "
                    "Either add it to your PATH or provide the Android SDK path."
                )

    def _extract_dex(self, apk_path: Path) -> Tuple[Path, Path]:
        """
        Extracts the primary `classes.dex` file from an APK.

        Args:
            apk_path: Path to the APK file.

        Returns:
            A tuple containing:
                - The path to the extracted `classes.dex` file in the temporary directory.
                - The path to the original APK file.

        Raises:
            FileNotFoundError: If the APK file does not exist.
            ValueError: If `classes.dex` is not found in the APK.
        """
        if not apk_path.is_file():
            raise FileNotFoundError(f"APK file not found: {apk_path}")

        output_dir = self.tmp_dir / apk_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)
        dex_output_path = output_dir / "classes.dex"

        try:
            with zipfile.ZipFile(apk_path, 'r') as apk_zip:
                if "classes.dex" in apk_zip.namelist():
                    with apk_zip.open("classes.dex") as source, open(dex_output_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    return dex_output_path, apk_path
                else:
                    raise ValueError(f"`classes.dex` not found in {apk_path}")
        except zipfile.BadZipFile:
            raise ValueError(f"Invalid ZIP file: {apk_path}")

    def _odex_file(self, dex_path: Path, output_apk_path: Path, bootclasspath: List[str] = None) -> Dict:
        """
        Odexes a DEX file using `dex2oat`.

        Args:
            dex_path: Path to the DEX file.
            output_apk_path: Path to the original APK (used for naming the output OAT file).
            bootclasspath: List of bootclasspath entries (e.g., framework JARs).

        Returns:
            A dictionary containing the status and any relevant messages/paths.
        """
        oat_output_path = self.tmp_dir / f"{output_apk_path.stem}.oat"
        vdex_output_path = self.tmp_dir / f"{output_apk_path.stem}.vdex"

        command = [
            self.dex2oat_path,
            "--dex-file=" + str(dex_path),
            "--output-oat-file=" + str(oat_output_path),
            "--oat-file-format=vdex",
            "--output-vdex-file=" + str(vdex_output_path),
            "--compiler-filter=speed",  # Optimize for speed (can be adjusted)
        ]

        if bootclasspath:
            command.append("--boot-image=" + ":".join(bootclasspath))  # Adjust for boot image if needed

        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            return {
                "status": "success",
                "message": f"Successfully odexed {dex_path.name}",
                "oat_path": oat_output_path,
                "vdex_path": vdex_output_path,
                "original_apk": output_apk_path,
            }
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "message": f"Error odexing {dex_path.name}: {e.stderr}",
                "original_apk": output_apk_path,
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"`dex2oat` not found. Ensure Android SDK path is correct or in PATH.",
                "original_apk": output_apk_path,
            }

    def _package_odex(self, original_apk_path: Path, oat_path: Path, vdex_path: Path, output_dir: Path = None) -> Dict:
        """
        Packages the generated OAT and VDex files back into a modified APK.

        Args:
            original_apk_path: Path to the original APK file.
            oat_path: Path to the generated OAT file.
            vdex_path: Path to the generated VDex file.
            output_dir: Directory to save the odexed APK. If None, saves in the current directory.

        Returns:
            A dictionary containing the status and the path to the odexed APK.
        """
        if output_dir is None:
            output_dir = Path(".")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_apk_name = f"{original_apk_path.stem}-odexed.apk"
        output_apk_path = output_dir / output_apk_name

        try:
            with zipfile.ZipFile(original_apk_path, 'r') as source_zip, \
                 zipfile.ZipFile(output_apk_path, 'w', zipfile.ZIP_DEFLATED) as target_zip:

                for item in source_zip.infolist():
                    buffer = source_zip.read(item.filename)
                    if item.filename != "classes.dex":  # Exclude the original DEX
                        target_zip.writestr(item, buffer)

                # Add the OAT and VDex files
                oat_arc_name = f"oat/{Path(oat_path).name[0]}/{Path(oat_path).name}"
                vdex_arc_name = f"oat/{Path(vdex_path).name[0]}/{Path(vdex_path).name}"
                target_zip.write(oat_path, oat_arc_name)
                target_zip.write(vdex_path, vdex_arc_name)

            return {"status": "success", "message": f"Odexed APK created at: {output_apk_path}", "output_path": output_apk_path}

        except zipfile.BadZipFile:
            return {"status": "error", "message": f"Error processing ZIP file: {original_apk_path}"}
        except FileNotFoundError as e:
            return {"status": "error", "message": f"Required file not found: {e}"}

    def odex_apk(self, apk_path: str, bootclasspath: List[str] = None, output_dir: str = None) -> Dict:
        """
        Odexes a single APK file.

        Args:
            apk_path: Path to the APK file.
            bootclasspath: List of bootclasspath entries (e.g., framework JARs).
            output_dir: Directory to save the odexed APK. If None, saves in the current directory.

        Returns:
            A dictionary containing the overall status and details of the operation.
        """
        apk_file = Path(apk_path)
        try:
            dex_path, original_apk = self._extract_dex(apk_file)
            odex_result = self._odex_file(dex_path, original_apk, bootclasspath)
            if odex_result["status"] == "success":
                package_result = self._package_odex(
                    odex_result["original_apk"], odex_result["oat_path"], odex_result["vdex_path"], Path(output_dir) if output_dir else None
                )
                return package_result
            else:
                return odex_result
        except (FileNotFoundError, ValueError) as e:
            return {"status": "error", "message": str(e), "original_apk": apk_file}
        finally:
            # Clean up temporary files for this APK
            temp_apk_dir = self.tmp_dir / apk_file.stem
            if temp_apk_dir.is_dir():
                shutil.rmtree(temp_apk_dir)
            if "oat_path" in locals() and Path(locals()["oat_path"]).is_file():
                os.remove(locals()["oat_path"])
            if "vdex_path" in locals() and Path(locals()["vdex_path"]).is_file():
                os.remove(locals()["vdex_path"])

    def deodex_apk(self, apk_path: str, output_dir: str = None) -> Dict:
        """
        Attempts to deodex an APK file (basic implementation, might not work for all cases).

        Warning: Deodexing is a complex process and this is a simplified attempt.
                 It relies on the assumption that the OAT/VDex files are present
                 in the APK and simply removes them and the `classes.dex` if it exists.
                 A true deodexer requires more sophisticated DEX merging and reconstruction.

        Args:
            apk_path: Path to the APK file.
            output_dir: Directory to save the deodexed APK. If None, saves in the current directory.

        Returns:
            A dictionary containing the status and the path to the attempted deodexed APK.
        """
        apk_file = Path(apk_path)
        if not apk_file.is_file():
            return {"status": "error", "message": f"APK file not found: {apk_file}"}

        if output_dir is None:
            output_dir = Path(".")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_apk_name = f"{apk_file.stem}-deodexed.apk"
        output_apk_path = output_dir / output_apk_name

        try:
            with zipfile.ZipFile(apk_file, 'r') as source_zip, \
                 zipfile.ZipFile(output_apk_path, 'w', zipfile.ZIP_DEFLATED) as target_zip:

                found_dex = False
                for item in source_zip.infolist():
                    if not item.filename.startswith("oat/") and item.filename != "classes.dex":
                        buffer = source_zip.read(item.filename)
                        target_zip.writestr(item, buffer)
                    elif item.filename == "classes.dex":
                        found_dex = True

                if not found_dex:
                    return {"status": "warning", "message": f"No classes.dex found in {apk_file}. Already deodexed?", "output_path": output_apk_path}

            return {"status": "success", "message": f"Attempted deodexed APK created at: {output_apk_path} (OAT/VDex removed)", "output_path": output_apk_path}

        except zipfile.BadZipFile:
            return {"status": "error", "message": f"Invalid ZIP file: {apk_path}"}

    def process_files(self, file_paths: List[str], operation: str = "odex", bootclasspath: List[str] = None, output_dir: str = None) -> List[Dict]:
        """
        Processes a list of APK or JAR files using multi-threading.

        Args:
            file_paths: A list of paths to APK or JAR files.
            operation: The operation to perform ("odex" or "deodex").
            bootclasspath: List of bootclasspath entries for Odexing.
            output_dir: Base directory to save the processed files.

        Returns:
            A list of dictionaries, where each dictionary contains the result
            of processing a single file.
        """
        results = []
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = []
            for file_path in file_paths:
                if operation == "odex":
                    futures.append(executor.submit(self.odex_apk, file_path, bootclasspath, output_dir))
                elif operation == "deodex":
                    futures.append(executor.submit(self.deodex_apk, file_path, output_dir))
                else:
                    results.append({"status": "error", "message": f"Invalid operation: {operation}", "original_file": file_path})

            for future in futures:
                results.append(future.result())

        return results

    def cleanup_tmp_dir(self):
        """
        Cleans up the temporary directory.
        """
        if self.tmp_dir.is_dir():
            shutil.rmtree(self.tmp_dir)
            self.tmp_dir.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    # Example Usage:

    # --- Configuration ---
    sdk_path = "/path/to/your/android/sdk"  # Replace with your actual SDK path or set to None if dex2oat is in PATH
    input_apks = ["app1.apk", "app2.apk"]  # Replace with your APK file paths
    output_directory = "processed_apks"
    boot_jars = [
        "/system/framework/core-oj.jar",
        "/system/framework/core-libart.jar",
        "/system/framework/framework.jar",
        "/system/framework/okhttp.jar",
        "/system/framework/telephony-common.jar",
        "/system/framework/voip-common.jar",
        # Add more bootclasspath JARs as needed for your target Android version
    ]

    # --- Initialize the Patcher ---
    try:
        patcher = OdexPatcherAdvanced(android_sdk_path=sdk_path, num_threads=2)
    except FileNotFoundError as e:
        print(f"Error initializing patcher: {e}")
        exit(1)

    # --- Perform Odexing ---
    print("\n--- Starting Odexing ---")
    odex_results = patcher.process_files(input_apks, operation="odex", bootclasspath=boot_jars, output_dir=output_directory)
    for result in odex_results:
        print(f"File: {result.get('original_apk', result.get('original_file', 'N/A'))}")
        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")
        if "output_path" in result:
            print(f"Output: {result['output_path']}")
        print("-" * 30)

    # --- Perform (Attempted) Deodexing ---
    print("\n--- Starting (Attempted) Deodexing ---")
    deodex_results = patcher.process_files([os.path.join(output_directory, f"{Path(apk).stem}-odexed.apk")
