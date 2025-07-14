# ![icon](https://i.imgur.com/2IBEmvZ.png)Rulescrape

**Rulescrape** is a Python GUI application for downloading images from booru-style imageboards. It supports tag-based filtering, optional exclusion of AI-generated content, multi-threaded downloads, duplicate skipping, skin/theme support, and real-time progress tracking.

---

## 🔧 Features

 - 📥 Download images by tag from `rule34` or `safebooru`
 - 🧠 Optional exclusion of AI-generated content via a checkbox
 - ⚡ Multi-threaded downloads (experimental)
 - 🎨 Modern dark-themed Tkinter GUI with skin/theme support
 - 📁 Automatically saves images to an `images/` folder, organized by site, extension, and tag
 - 🗂️ Multiple organization methods: by extension, by tag, flat, or both
 - 🚫 Skips duplicate images
 - 🛠️ Enhanced error handling and logging
 - ⚙️ Configurable user settings (saved between runs)

---

## 📸 Screenshot

![Screenshot of the Tkinter GUI](https://i.imgur.com/Z2QOQRe.png)

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
- Python 3.13+
- Recommended: Virtual environment

#### Steps
1. Install dependencies:
   ```sh
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
   > If `requirements.txt` is missing, install manually:
   ```sh
   pip install requests tqdm
   ```
2. Run the script:
   ```sh
   python rulescrape.py
   ```

---

## 🚀 Usage

### In the GUI:

1. **Select Site** – Choose between `rule34` or `safebooru`
2. **Enter Tag** – (Optional) Enter a tag like `cat_girl`
3. **Set Limit** – Enter how many images to download (default is 10; both sites support a maximum of 1000)
4. **Organization Method** – Choose how images are organized (by extension, tag, flat, or both)
5. **Anti-AI Tags** – Check this box to automatically exclude AI-generated content
6. **Multi-threaded Downloads** – (Experimental) Enable for faster downloads (progress bar may be less accurate)
7. **Start Download** – Click to begin downloading

Downloaded images will be saved in:

```
images/rule34/<extension>/<tag>/
images/safebooru/<extension>/<tag>/
```
Or other folder structures depending on the selected organization method.

---
#### CLI Mode

> **Note:** CLI mode is only available when running the Python file directly (e.g., `python rulescrape.py`).  
> It is **not** supported in the compiled GUI executable.

```bash
python rulescrape.py --cli --booru_type rule34 --tag cat_girl --limit 20 --anti_ai true --multithread --max_workers 8
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
- Avoid excessive downloads to prevent IP bans (max 1000 images per request)

---

## 🐞 Troubleshooting

- **Invalid JSON response**  
  - The site may be down or rate-limiting your IP.

- **No downloads**  
  - Check that your tag is valid and has available content.
---

## 📌 Planned Features

> 🔜 Future updates may include:
> - Refactoring code for more modular booru additions.
> - ~~Further improvements to error handling and progress tracking~~ (Implemented in version 1.2)
> - ~~More advanced duplicate detection~~ (Implemented in version 1.2)
> - ~~Additional skin/theme options~~ (Implemented in version 1.2)

---

## 📜 License

This project is open-source and available under the [MIT License](https://opensource.org/license/MIT).

---

## 🙋 Contributing

Feel free to fork the project, open issues, or submit pull requests. Contributions are always welcome!
