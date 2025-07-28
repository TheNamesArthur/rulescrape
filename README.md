# ![icon](https://i.imgur.com/2IBEmvZ.png)Rulescrape

**Rulescrape** is a Python GUI application for downloading images from booru-style imageboards. It supports tag-based filtering, optional exclusion of AI-generated content, multi-threaded downloads, duplicate skipping, skin/theme support, and real-time progress tracking.

---

## 🔧 Features

 - 📥 Download images by tag from `rule34`, `safebooru`, `danbooru`, or `yande.re`
 - 🧠 Optional exclusion of AI-generated content via a checkbox
 - ⚡ Multi-threaded downloads with intelligent worker management
 - 🎨 Modern dark-themed Tkinter GUI with advanced skin/theme support
 - 📁 Automatically saves images to an `images/` folder, organized by site, extension, and tag
 - 🗂️ Multiple organization methods: by extension, by tag, flat, or both
 - 🚫 Advanced duplicate detection using MD5 hash checking
 - 🛠️ Enhanced error handling, logging, and progress tracking
 - ⚙️ Configurable user settings with persistent storage
 - 🔄 Unified download module for consistent CLI and GUI behavior
 - 🎯 Smart pagination and retry logic for reliable downloads

---

## 📸 Screenshot

![Screenshot of the Tkinter GUI](https://i.imgur.com/tUh4nVe.png)

---

## 🖥️ Installation

### Option 1: Compiled Executable (Recommended for End Users)

#### Requirements
- Windows or Linux
- No Python installation needed

#### Steps
1. Download the compiled executable for your platform (or build it yourself using PyInstaller).
2. Place the executable in your desired image directory for convenience.
3. Run it:
   - Double-click the file
   - Or launch via terminal:
     ```sh
     ./rulescrape
     ```

---

### Option 2: Python Source (For Developers and Power Users)

#### Requirements
- Python 3.8+
- Recommended: Virtual environment

#### Steps
1. Install dependencies:
   ```sh
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Run the script:
   ```sh
   python rulescrape.py
   ```

---

## 🚀 Usage

### In the GUI:

1. **Select Site** – Choose between `rule34`, `safebooru`, `danbooru`, or `yande.re`
2. **Enter Tag** – (Optional) Enter a tag like `cat_girl`
3. **Set Limit** – Enter how many images to download (default is 10; rule34 supports up to 1000, others may have different limits)
4. **Organization Method** – Choose how images are organized (by extension, tag, flat, or both)
5. **Anti-AI Tags** – Check this box to automatically exclude AI-generated content
6. **Multi-threaded Downloads** – Enable for faster downloads with intelligent worker management
7. **Start Download** – Click to begin downloading

Downloaded images will be saved in:

```
images/rule34/<extension>/<tag>/
images/safebooru/<extension>/<tag>/
images/danbooru/<extension>/<tag>/
images/yande.re/<extension>/<tag>/
```
Or other folder structures depending on the selected organization method.

---
#### CLI Mode

> **Note:** CLI mode is only available when running the Python file directly (e.g., `python rulescrape.py`).  
> It is **not** supported in the compiled GUI executable.

```bash
python rulescrape.py --cli --booru_type danbooru --tag cat_girl --limit 20 --anti_ai true --multithread --max_workers 8
```

---

## 🧠 Anti-AI Tagging

When Anti-AI is enabled, the following tags are appended to your search:

```diff
-ai -ai_generated -ai_assisted
```

This helps reduce the appearance of AI-generated content in results—especially useful on rule34.

---

## 🛠️ Notes

- This tool **does not** bypass API-imposed filters or content restrictions
- Always respect the terms of use of each site
- Danbooru enforces rate limits (10 requests/second for all users)
- Different sites have different image limits per request (rule34: 1000, others vary)
- Advanced duplicate detection prevents re-downloading the same content
- Multi-threaded downloads use intelligent worker management for optimal performance

---

## 🐞 Troubleshooting

- **Invalid JSON response**  
  - The site may be down or rate-limiting your IP.

- **No downloads**  
  - Check that your tag is valid and has available content.

- **Danbooru rate limit errors**
  - Danbooru enforces strict rate limits. The app includes automatic retry logic.

- **Duplicates not being detected**
  - Ensure the duplication checker has scanned existing images on startup.
---

## 📌 V1.5 Development Features

>  **Current V1.5 Branch Improvements:**
> - ✅ **Advanced Duplicate Detection** - MD5 hash-based system prevents re-downloading identical files
> - ✅ **Unified Download Module** - Consistent behavior between CLI and GUI modes
> - ✅ **Extended Booru Support** - Added Danbooru and Yande.re support
> - ✅ **Smart Pagination** - Automatic retry logic and intelligent post fetchings
> - ✅ **Enhanced Multi-threading** - Improved worker management and progress tracking
> - ✅ **Rate Limit Handling** - Automatic retry with backoff for Danbooru API limits
> - ✅ **Modular Architecture** - Separated concerns for better maintainability

> 🔜 **Planned for Future Versions:**
> - Additional booru site integrations
> - Enhanced progress reporting and download statistics
> - Batch download management
> - Custom filter and tag management

---

## 🆚 V1.5 vs Main Branch Comparison

### New in V1.5:

#### 🔧 **Core Enhancements**
- **Advanced Duplicate Detection**: Complete MD5 hash-based duplication system (`dupe_check.py`)
- **Unified Download Architecture**: Centralized download logic in `download.py` for consistency
- **Extended Booru Support**: Added Danbooru and Yande.re APIs alongside Rule34 and Safebooru

#### 🏗️ **Architecture Improvements**
- **Modular Design**: Separated download logic from GUI and CLI components
- **Smart Download Manager**: Intelligent pagination, retry logic, and worker management
- **Enhanced Error Handling**: Better API error detection and user feedback

#### ⚡ **Performance Features**
- **Intelligent Multi-threading**: Improved worker allocation and progress tracking
- **Rate Limit Management**: Automatic retry with exponential backoff for API limits
- **Memory-Efficient Scanning**: Optimized existing image scanning for duplicate detection

#### 📊 **Statistics**
- **1,282 lines added, 391 lines removed** across 7 files (main → V1.5)
- **New Files**: `download.py`, `dupe_check.py` 
- **Major Enhancements**: `gui.py`, `booru_api.py`, `rulescrape.py`
- **Total V1.5 Codebase**: 1,855 lines across 5 core Python files

### Differences from Main Branch:
- **Main**: Basic dual-booru support (Rule34/Safebooru only)
- **V1.5**: Four-booru ecosystem with advanced features
- **Main**: Simple duplicate filename checking
- **V1.5**: Content-aware MD5 hash duplicate detection
- **Main**: Basic multi-threading
- **V1.5**: Intelligent worker management with progress reservation

---

## 📜 License

This project is open-source and available under the [MIT License](https://opensource.org/license/MIT).

---

## 🙋 Contributing

Feel free to fork the project, open issues, or submit pull requests. Contributions are always welcome!
