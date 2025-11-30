<h1 align="center">
  <img src="https://raw.githubusercontent.com/kekkodance/cropper/main/icon.ico" width="40">
  cropper
</h1>
<p align="center">
<strong>A tool to easily create cropped or blurred/pixelated versions of your artwork.</strong>
</p>

---

<img width="1202" height="852" alt="29upm9" src="https://github.com/user-attachments/assets/ee874703-7c45-46aa-bf46-8f14f1d0d3c9" />

---

<br>
Meant to fullfill a purpose, that of creating cropped / obfuscated versions of art to then post onto Patreon, because an entire drawing as the blurred preview is too revealing.
<br><br>

---

<img width="1202" height="852" alt="yipqts" src="https://github.com/user-attachments/assets/d17f66ff-acbf-415a-b911-9430f8ea9e8c" />  

&nbsp;

<p><strong>You can download it (for Windows) in the <a href="https://github.com/kekkodance/cropper/releases/latest"><i>Releases</i></a> section.</strong></p>

---

**If you wish to build this yourself instead, use nuitka with this command:**

```sh
nuitka --onefile --windows-icon-from-ico=icon.ico --include-data-file=icon.ico=icon.ico --include-data-file=icon.png=icon.png --remove-output --nofollow-import-to=test --nofollow-import-to=distutils --nofollow-import-to=setuptools --nofollow-import-to=numpy --lto=yes --enable-plugin=tk-inter --mingw64 --windows-console-mode=disable cropper.py
```
