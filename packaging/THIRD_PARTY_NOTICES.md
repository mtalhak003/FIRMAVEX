# Distribution candidate notices

FIRMAVEX code: MIT (included LICENSE). Python is distributed under the PSF license.
PyInstaller 6.16.0: GPL with bootloader exception (included COPYING.txt); source
https://github.com/pyinstaller/pyinstaller/tree/v6.16.0 .
pyelftools: public domain/BSD portions (included LICENSE).
Qt/PySide6/Shiboken: LGPL v3/GPL/commercial choices. Included GNU license texts
were obtained from Qt's qtbase LICENSES repository. These candidates use dynamic
Qt libraries: users may replace them with compatible versions. No restriction on
reverse engineering for debugging such modifications is imposed by FIRMAVEX.
Qt source: https://download.qt.io/official_releases/qt/ ; PySide source:
https://code.qt.io/pyside/pyside-setup.git/ . Exact executing package versions are
recorded in distribution-manifest.json. Rebuild the application from this Git
revision using packaging/desktop.spec and the recorded dependencies.

These links and notices do NOT complete the component-by-component license or
corresponding-source audit. PyInstaller dependency collection can include other
libraries with their own terms. Complete that inventory and archive exact
corresponding source before public release; these are development candidates.
No QEMU/GDB/GCC binaries are bundled in the application. Runtime packs need their
own dependency/license/source inventory. No vendor runtime pack is supplied.
