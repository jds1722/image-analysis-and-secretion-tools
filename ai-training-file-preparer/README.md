# AI Training File Preparer

Small Windows-friendly Tkinter app for preparing AI training files.

The app lets you choose a source folder, paste a list of filenames, find matching files, and copy them into a destination folder.

## Run

From the workspace root:

```powershell
tif\.venv\Scripts\python.exe ai-training-file-preparer\training_file_preparer_ui.py
```

If Python is installed globally:

```powershell
python ai-training-file-preparer\training_file_preparer_ui.py
```

## Input List

Paste one filename per line:

```text
image_001.tif
image_002.tif
labels.csv
```

Comma-separated names also work:

```text
image_001.tif, image_002.tif, labels.csv
```

## Options

- Search subfolders: recursively search under the selected source folder.
- Case-sensitive filename match: match filenames exactly by case.
- Copy every match when duplicates exist: copy all files with the requested name if it appears in multiple folders.
- Overwrite existing destination files: replace files already present in the destination folder.

When overwrite is off, existing destination files are kept and new copies receive names like `file_copy1.tif`.

## Output

Copied files are written to the selected destination folder. A CSV report named `file_copy_report_YYYYMMDD_HHMMSS.csv` is written there too.

## 8x TIF Augmentation

Use `augment_training_images.py` to make AI training copies from TIF/TIFF images.

For each source image, it writes:

- original
- 90 degree rotation
- 180 degree rotation
- 270 degree rotation
- left-right flipped original
- left-right flipped 90 degree rotation
- left-right flipped 180 degree rotation
- left-right flipped 270 degree rotation

Run it on one file:

```powershell
tif\.venv\Scripts\python.exe ai-training-file-preparer\augment_training_images.py "C:\path\to\image.tif" "C:\path\to\output"
```

Run it on every TIF/TIFF in a folder:

```powershell
tif\.venv\Scripts\python.exe ai-training-file-preparer\augment_training_images.py "C:\path\to\source_folder" "C:\path\to\output" --recursive
```

Use `--overwrite` if you want to replace existing augmented files.

### Augmentation UI

Run the UI when you want to choose the input and output paths with folder/file browser dialogs:

```powershell
tif\.venv\Scripts\python.exe ai-training-file-preparer\augment_training_images_ui.py
```
