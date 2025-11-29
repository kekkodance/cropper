# cropper
**A tool that easily creates cropped versions of artwork.**

---

Meant to fullfill a purpose, that of creating cropped versions of art to then post onto Patreon, as setting an entire artwork as the blurred preview is too revealing.

---

**If you wish to build this yourself, use pyinstaller with this command:**

```sh
pyinstaller --onefile --windowed --icon=icon.ico --add-data "icon.ico;." --name "Cropper" --optimize 2 --clean cropper.py
```
