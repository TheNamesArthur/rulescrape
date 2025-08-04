# ![icon](https://i.imgur.com/2IBEmvZ.png)Rulescrape

**Rulescrape** is a modern Python application for downloading images from booru-style imageboards. Features a CustomTkinter GUI with animated previews, multithreaded downloads, intelligent duplicate detection, and comprehensive download management.

---

## 🔧 Features

### 🎨 Modern Interface
 - **CustomTkinter GUI** with tabbed design (Downloads, Gallery, History, Settings)
 - **Animated Previews** - Hover over GIFs and videos to see animated previews (up to 20 frames for GIFs, 15 frames for videos)
 - **Dark/Light Theme** switching with persistent settings
 - **Progressive Gallery Loading** with disk-based thumbnail caching
 - **Real-Time Progress** tracking during downloads

### 📥 Download Management  
 - Download images by tag from `rule34`, `safebooru`, `danbooru`, `yande.re`, or `paheal`
 - **Multi-tag Support** with space-separated tag input
 - **Multithreaded Downloads** with configurable worker threads
 - **Download History** tracking with timestamps and status
 - **Pause/Resume Downloads** with full session control
 - **Blacklist System** with CLI management for filtering unwanted content

### 🧠 Smart Features
 - **AI Content Filtering** - Optional exclusion of AI-generated content using `-ai -ai_generated -ai_assisted` tags
 - **MD5-Based Duplicate Detection** with multithreaded scanning of existing images
 - **Multiple Organization Methods** - by extension and first tag, extension only, or flat structure
 - **Disk-Based Thumbnail Cache** - persistent 500MB cache with intelligent cleanup and LRU eviction
 - **Automatic Retry Logic** with exponential backoff for failed requests

### 🛠️ Technical Features
 - **Configuration System** using INI files with automatic defaults
 - **Compressed Log Rotation** with automatic daily log archiving
 - **Cross-Platform Support** (Windows, Linux, macOS)
 - **Memory Optimized** with disk caching instead of memory-based thumbnails
 - **CLI Mode** with comprehensive blacklist management commands

---

## 📸 Screenshots

### Modern CustomTkinter Interface
![Modern GUI Screenshot](https://i.imgur.com/qCIpeIC.png)

### Animated Gallery Previews
*Hover over GIFs and videos in the gallery to see animated previews in real-time*

### Download Management
*Advanced download controls with pause/resume, real-time progress, and comprehensive history tracking*

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
- **GUI Dependencies**: `customtkinter`, `pillow`, `requests`, `tqdm`
- **Video Support**: `opencv-python` (for actual video thumbnails, falls back to placeholders if not installed)
- Recommended: Virtual environment

#### Steps
1. Install dependencies:
   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   
   # Or install manually:
   pip install customtkinter pillow requests tqdm
   pip install opencv-python  # For video thumbnails, recommended
   ```
2. Run the modern GUI:
   ```sh
   python rulescrape.py
   ```
   The application will automatically launch the modern CustomTkinter GUI.

---

## 🚀 Usage

### Modern GUI Interface:

#### Downloads Tab
1. **Quick Download Section** (Sidebar)
   - Choose booru site: `rule34`, `safebooru`, `danbooru`, `yande.re`, or `paheal`
   - Enter tags (optional - leave empty for recent images)
   - Set download limit and click "Quick Download"

2. **Advanced Download Section**
   - Multi-line tag input (space-separated tags)
   - **Anti-AI Content** - Automatically adds `-ai -ai_generated -ai_assisted` to search
   - **Multi-threaded Downloads** - Configurable worker threads (default: half of CPU cores)
   - **Pause/Resume** - Full download session management with cancel support
   - **Real-time Progress** - Live download statistics with file counts

#### Gallery Tab
- **Animated Previews** - Hover over GIFs and videos for frame-by-frame animation (cached up to 30 animations)
- **Progressive Loading** - Thumbnails load in configurable batches for responsive experience
- **Extension Filtering** - Filter gallery by file type (All, Images, Videos, GIFs)
- **Disk-Based Caching** - 500MB persistent thumbnail cache with automatic cleanup

#### History Tab
- **Download History** with timestamps, booru site, tags, file counts, and completion status
- **Persistent Storage** - History saved across application sessions
- **Status Tracking** - Shows Completed, Failed, or Cancelled status for each download

#### Settings Tab
- **Performance Tuning** - Disk cache size (MB), worker threads (default: half of CPU cores), gallery batch sizes
- **Interface Options** - Theme switching (Dark/Light mode)
- **Download Behavior** - Organization methods, anti-AI filtering
- **Cache Management** - Clear cache, show statistics, optimize cache storage

### Disk Cache Storage
The application uses a disk-based thumbnail cache system:
- **Storage Location**: `cache/thumbnails/` directory in your images folder
- **Cache Size**: 500MB default with intelligent cleanup when limit exceeded
- **Persistence**: Thumbnails persist across application sessions
- **Benefits**: Faster startup, lower memory usage, improved performance
- **Management**: Automatic LRU eviction, manual optimization available in Settings

### Theme Switching
Toggle between **Dark Mode** and **Light Mode** with the sidebar switch. Settings persist across sessions.

Downloaded images are organized as:
```
images/rule34/<extension>/<first_tag>/
images/safebooru/<extension>/<first_tag>/
images/danbooru/<extension>/<first_tag>/
images/yande.re/<extension>/<first_tag>/
images/paheal/<extension>/<first_tag>/
```

---
#### CLI Mode

<!-- > **Note:** CLI mode is available when running the Python file directly with the `--cli` flag. -->

```bash
# Basic CLI usage
python rulescrape.py --cli --booru_type rule34 --tag cat_girl --limit 20

# Advanced CLI with multithreading
python rulescrape.py --cli --booru_type danbooru --tag "cat_girl 1girl" --limit 50 \
  --anti_ai true --multithread --max_workers 8

# Blacklist management
python rulescrape.py --blacklist-add "unwanted_tag"
python rulescrape.py --blacklist-list
python rulescrape.py --blacklist-enable

# Download recent images without tags
python rulescrape.py --cli --booru_type rule34 --limit 30
```

**CLI Arguments:**
- `--cli` - Force CLI mode (required for command-line usage)
- `--booru_type` - Site: rule34, safebooru, danbooru, yande.re, paheal
- `--tag` - Search tags (space-separated, optional)
- `--limit` - Number of images to download (1-1000)
- `--anti_ai` - Exclude AI content (true/false)
- `--multithread` - Enable multi-threaded downloads
- `--max_workers` - Number of download threads
- `--org_method` - File organization method

**Blacklist CLI Commands:**
- `--blacklist-add TAG` - Add tag to blacklist
- `--blacklist-remove TAG` - Remove tag from blacklist  
- `--blacklist-list` - Show all blacklisted tags
- `--blacklist-stats` - Show blacklist statistics
- `--blacklist-enable/--blacklist-disable` - Toggle blacklist filtering

---

## 🧠 Anti-AI Tagging

When Anti-AI is enabled, the following tags are appended to your search:

```diff
-ai -ai_generated -ai_assisted
```

This helps reduce the appearance of AI-generated content in results—especially useful on rule34.

---

## 🛠️ Advanced Features & Technical Details

### 🎞️ Animated Previews
- **GIF Animation** - Hover over GIF thumbnails to see up to 20 frames in sequence
- **Video Thumbnails** - Automatic thumbnail generation from MP4/WebM using OpenCV (10% position)
- **Memory Management** - Preview cache limited to 30 animations with FIFO eviction
- **Frame Extraction** - Smart frame sampling for smooth preview experience (~8fps playback)

### 🔧 Performance & Caching
- **Disk Thumbnail Cache** - 500MB persistent cache with PNG compression
- **Multithreaded Processing** - Configurable workers (default: half of CPU cores) for thumbnail generation  
- **Progressive Loading** - Gallery loads in batches (default: 12 items) for responsive UI
- **LRU Eviction** - Automatic cleanup when cache exceeds size limit (reduces to 80% capacity)

### 🔄 Download Management
- **Session Control** - Pause/resume downloads with proper thread management
- **Exponential Backoff** - Automatic retry logic for rate-limited APIs (5 retries max)
- **Progress Reporting** - Real-time callbacks for GUI integration
- **Cancellation Support** - Clean thread shutdown and resource cleanup

### 📊 Duplicate Detection
- **MD5 Hash Comparison** - Content-based duplicate detection across all images
- **Multithreaded Scanning** - Fast existing image scanning on startup
- **Session Tracking** - Counts duplicates found during current download session
- **Atomic Downloads** - Temporary file system prevents corrupted partial downloads

### 🏷️ Blacklist System
- **Tag Filtering** - Server-side filtering using blacklisted tags
- **CLI Management** - Complete command-line interface for blacklist operations
- **Persistent Storage** - JSON-based blacklist configuration
- **Statistics** - Detailed reporting on filtering effectiveness

### 🔒 Technical Implementation
- **Thread Safety** - Proper synchronization for concurrent operations
- **Resource Management** - Automatic cleanup of threads and file handles
- **Cross-Platform** - Consistent behavior on Windows, Linux, and macOS
- **Configuration** - INI-based settings with automatic migration and defaults

---

## 🐞 Troubleshooting

### Common Issues

**GUI Dependencies Error**
```
ImportError: No module named 'customtkinter'
```
- Install GUI dependencies: `pip install customtkinter pillow requests tqdm`

**Animated Previews Not Working**
- Install OpenCV for video support: `pip install opencv-python`
- Check Settings tab → Enable animated previews

**Slow Gallery Loading**
- Adjust performance settings in Settings tab
- Reduce thumbnail cache size or batch size
- Clear thumbnail cache and restart

**Download Issues**
- **Invalid JSON response**: Site may be down or rate-limiting
- **No downloads**: Check tag validity and site availability  
- **Rate limit errors**: Built-in retry logic will handle this automatically
- **Duplicates not detected**: Ensure duplicate scanner completed initial scan

**Performance Issues**
- **High memory usage**: Reduce thumbnail cache size in Settings (500MB default)
- **Slow gallery loading**: Reduce gallery batch size or worker thread count
- **UI responsiveness**: Disable animated previews or reduce preview cache size (30 max)

**Cache Issues**  
- **Gallery not updating**: Use "Clear Cache" in Settings tab or restart application
- **Disk space concerns**: Check cache statistics and optimize cache to remove orphaned files
- **Thumbnail errors**: Ensure PIL and OpenCV are properly installed for image/video processing

### Configuration Files
- **Settings**: `cli.config` (INI format with user preferences)
- **Blacklist**: `blacklist.json` (JSON format with filtered tags)
- **Logs**: `logs/rulescrape.log` (compressed daily rotation)
- **Cache**: `cache/thumbnails/` (PNG thumbnails with JSON metadata)
---

## 📌 Current V1.5 Features

**✅ Implemented Features:**
- **Modern CustomTkinter GUI** - Complete interface with tabbed design
- **Animated Preview System** - Hover animations for GIFs (20 frames) and videos (15 frames) 
- **Disk-Based Thumbnail Cache** - 500MB persistent storage with intelligent cleanup
- **Multithreaded Downloads** - Configurable worker management with pause/resume
- **Advanced Duplicate Detection** - MD5 hash-based with multithreaded scanning
- **Comprehensive Blacklist System** - CLI management with persistent JSON storage
- **Theme Switching** - Dark/light mode toggle with persistent settings
- **Download History** - Persistent tracking with timestamps and status
- **Organization Methods** - By extension and first tag, extension only, or flat structure
- **Cross-Platform Support** - Windows, Linux, and macOS compatibility
- **Progressive Gallery Loading** - Batched thumbnail loading for responsive UI
- **Comprehensive Logging** - Compressed daily log rotation with detailed debugging

**🔄 Current Architecture:**
- **Modular Core Package** - 8 specialized modules (6,000+ lines total)
- **Unified Settings System** - INI-based configuration with automatic defaults
- **Thread-Safe Operations** - Proper synchronization for concurrent downloads
- **Resource Management** - Automatic cleanup and memory optimization

---

## 🆚 Architecture Overview

### Core Modules (V1.5):
- **`core/gui.py`** (3,128 lines) - Modern CustomTkinter interface with tabbed design
- **`core/download.py`** (677 lines) - Unified download management with threading support
- **`core/thumbnail_cache.py`** (559 lines) - Disk-based caching system with LRU eviction
- **`core/blacklist.py`** (547 lines) - Comprehensive tag filtering and CLI management
- **`core/booru_api.py`** (357 lines) - Multi-site API integration (rule34, danbooru, etc.)
- **`core/animated_preview.py`** (290 lines) - GIF/video animation system with frame caching
- **`core/dupe_check.py`** (257 lines) - MD5-based duplicate detection with multithreading

### Key Improvements from Previous Versions:
- **Modular Architecture**: Separated concerns into specialized modules
- **Modern UI Framework**: Migrated from basic Tkinter to CustomTkinter
- **Persistent Caching**: Disk-based thumbnails replace memory-only caching
- **Enhanced Performance**: Multithreaded operations throughout
- **Better Error Handling**: Comprehensive logging and user feedback
- **Configuration Management**: INI-based settings with automatic migration

---

## 📜 License

This project is open-source and available under the [MIT License](https://opensource.org/license/MIT).

---

## 🙋 Contributing

Feel free to fork the project, open issues, or submit pull requests. Contributions are always welcome!
