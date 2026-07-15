# Publishing LinuxShot on Flathub

The manifest lives at `flatpak/io.github.taintedangel.linuxshot.yml`.
It has **not been through a full build yet** - flatpak-builder wasn't
available on the dev machine - so expect to iterate on it during step 1.

## 1. Build and test locally

```bash
sudo pacman -S flatpak-builder          # or distro equivalent
flatpak install flathub org.kde.Platform//6.8 org.kde.Sdk//6.8 \
    io.qt.PySide.BaseApp//6.8

flatpak-builder --user --install --force-clean build \
    flatpak/io.github.taintedangel.linuxshot.yml
flatpak run io.github.taintedangel.linuxshot
```

Things to verify inside the sandbox:

- Capture works (it must go through the desktop portal - the sandbox
  has no spectacle/grim/maim)
- Clipboard copy works (bundled wl-clipboard)
- Tray icon appears, uploads work, notifications show

## 2. Validate the metadata

```bash
flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
    manifest flatpak/io.github.taintedangel.linuxshot.yml
flatpak run --command=appstreamcli org.flatpak.Builder \
    validate resources/io.github.taintedangel.linuxshot.metainfo.xml
```

## 3. Submit

1. Fork https://github.com/flathub/flathub and branch from `new-pr`
2. Add the manifest (submissions pin a git tag: change the linuxshot
   module's `dir` source to a `git` source pointing at the release tag)
3. Open a PR against the `new-pr` branch; reviewers usually respond
   within a week
4. Once merged, Flathub creates a dedicated repo and you get push
   access for future updates

Full docs: https://docs.flathub.org/docs/for-app-authors/submission
