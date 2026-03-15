PREFIX ?= /usr/local
BINDIR = $(PREFIX)/bin
APPDIR = $(PREFIX)/share/applications
ICONDIR = $(PREFIX)/share/icons/hicolor/scalable/apps

.PHONY: all install uninstall dev clean

all:
	@echo "LinuxShot - ShareX-inspired screenshot tool for Linux"
	@echo ""
	@echo "Usage:"
	@echo "  make install       Install system-wide (requires sudo)"
	@echo "  make uninstall     Remove system-wide install"
	@echo "  make dev           Install in development mode (editable)"
	@echo "  make clean         Remove build artifacts"
	@echo ""
	@echo "Or use ./setup.sh for a guided installation."

install:
	pip install --break-system-packages .
	install -Dm644 resources/linuxshot.desktop $(DESTDIR)$(APPDIR)/linuxshot.desktop
	@echo ""
	@echo "LinuxShot installed successfully!"
	@echo "Run 'linuxshot --help' to get started."

uninstall:
	pip uninstall -y linuxshot
	rm -f $(DESTDIR)$(APPDIR)/linuxshot.desktop
	@echo "LinuxShot uninstalled."

dev:
	pip install --break-system-packages -e .
	@echo "LinuxShot installed in development mode."

clean:
	rm -rf build/ dist/ *.egg-info linuxshot/*.pyc linuxshot/__pycache__
	rm -rf linuxshot/ui/__pycache__
	@echo "Cleaned build artifacts."
