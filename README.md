# ![icon](https://i.imgur.com/2IBEmvZ.png)Rulescrape

**Rulescrape** is a Python GUI application for downloading images from booru-style imageboards, specifically [rule34.xxx](https://rule34.xxx) and [safebooru.org](https://safebooru.org). It supports tag-based filtering, optional exclusion of AI-generated content, and real-time progress tracking.

---

## 🔧 Features

- 📥 Download images by tag from `rule34` or `safebooru`
- 🧠 Optional exclusion of AI-generated content via a checkbox
- 🎨 Modern dark-themed Tkinter GUI with tooltips
- 📁 Automatically saves images to an `images/` folder, organized by site

---

## 📸 Screenshot

![Screenshot of the Tkinter GUI](https://i.imgur.com/Z2QOQRe.png)

---

## 🚀 Usage

After downloading the program, simply run the executable file:

```bash
./rulescrape (Linux)
```

```cmd
rulescrape.exe (Windows)
```

### In the GUI:

1. **Select Site** – Choose between `rule34` or `safebooru`
2. **Enter Tag** – (Optional) Enter a tag like `cat_girl`
3. **Set Limit** – Enter how many images to download (default is 10; both sites support a maximum of 1000)
4. **Anti-AI Tags** – Check this box to automatically exclude AI-generated content
5. **Start Download** – Click to begin downloading

Downloaded images will be saved in:

```
images/rule34/
images/safebooru/
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

- **GUI freezing**  
  - May be caused by a slow network or server issue.

---

## 📌 Planned Features

> 🔜 Future updates include:
> - Improved support for more boorus ([rule34.xxx](https://rule34.xxx) and [safebooru](https://safebooru.org) are currently hardcoded.)
> - Multi-threaded downloads
> - Improved organization
> - Skipping duplicate posts
> - Enhanced error handling and logging  
> - Skin/theme support  
> - Configurable user settings

---

## 📜 License

This project is open-source and available under the [MIT License](https://opensource.org/license/MIT).

---

## 🙋 Contributing

Feel free to fork the project, open issues, or submit pull requests. Contributions are always welcome!
