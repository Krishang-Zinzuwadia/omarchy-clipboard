import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import qs.Commons
import qs.Ui
import "ClipboardHistory.js" as History

Item {
  id: root

  property string pluginDir: Quickshell.env("HOME") + "/.config/omarchy/plugins/io.github.krishang-zinzuwadia.omarchy-clipboard"
  property string stateDir: Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state/omarchy-clipboard"
  property string historyPath: stateDir + "/history.json"
  property string bootId: ""
  property bool opened: false
  property string filterText: ""
  property int selectedIndex: 0
  property bool resetViewport: false
  property bool deleteConfirmation: false
  property bool historyDirty: false
  property var history: []
  property var rows: []

  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color border: Color.menu.border
  property color selectedBackground: Color.menu.selectedBackground
  property color selectedText: Color.menu.selectedText
  property color scrim: Color.menu.scrim

  function open() {
    opened = true
    filterText = ""
    selectedIndex = 0
    resetViewport = true
    rebuild()
    Qt.callLater(function() { keyboard.forceActiveFocus() })
  }
  function close() { deleteConfirmation = false; opened = false }
  function toggle() { opened ? close() : open() }
  function rebuild() {
    rows = History.ordered(history, filterText)
    model.clear()
    for (var i = 0; i < rows.length; i++) {
      var entry = rows[i].entry
      model.append({
        historyIndex: rows[i].historyIndex, kind: entry.kind, entryText: entry.text || "",
        path: entry.path || "", mime: entry.mime || "", pinned: entry.pinned
      })
    }
    if (selectedIndex >= model.count) selectedIndex = Math.max(0, model.count - 1)
    Qt.callLater(function() {
      if (!model.count) return
      list.currentIndex = selectedIndex
      if (resetViewport) {
        list.positionViewAtIndex(0, ListView.Beginning)
        resetViewport = false
      } else {
        list.positionViewAtIndex(selectedIndex, ListView.Contain)
      }
    })
  }
  function load(raw) { history = History.parseState(raw, bootId); rebuild() }
  function save() {
    historyDirty = true
    historyWrite.pending = JSON.stringify({ bootId: bootId, items: history }) + "\n"
    if (!historyWrite.running) historyWrite.running = true
  }
  function addEntry(raw) {
    if (String(raw).length > 100000) return
    try { history = History.add(history, JSON.parse(raw), 300); save(); rebuild() } catch (error) {}
  }
  function move(delta) {
    if (!model.count) return
    selectedIndex = (selectedIndex + delta + model.count) % model.count
    list.currentIndex = selectedIndex
    list.positionViewAtIndex(selectedIndex, ListView.Contain)
  }
  function copy(index) {
    if (index < 0 || index >= model.count) return
    var entry = model.get(index)
    copyProc.payload = JSON.stringify({
      kind: entry.kind, text: entry.entryText, path: entry.path, mime: entry.mime
    })
    copyProc.command = [pluginDir + "/copy-entry.sh", "--entry"]
    copyProc.running = true
    close()
  }
  function togglePin(index) {
    if (index < 0 || index >= model.count) return
    var item = history[model.get(index).historyIndex]
    item.pinned = !item.pinned
    save(); rebuild()
  }
  function deleteCurrent() {
    if (!model.count) return
    deleteConfirmation = model.get(selectedIndex).pinned
    if (!deleteConfirmation) removeCurrent()
  }
  function removeCurrent() {
    if (!model.count) return
    history.splice(model.get(selectedIndex).historyIndex, 1)
    selectedIndex = Math.max(0, selectedIndex - (selectedIndex === model.count - 1 ? 1 : 0))
    deleteConfirmation = false
    save(); rebuild()
  }

  Component.onCompleted: { bootProc.running = true }

  ListModel { id: model }
  Process {
    id: historyRead
    command: [root.pluginDir + "/history-io.sh", "read"]
    stdout: StdioCollector { onStreamFinished: root.load(text) }
  }
  Process {
    id: historyWrite
    property string pending: ""
    property string writing: ""
    command: [root.pluginDir + "/history-io.sh", "write"]
    stdinEnabled: true
    onStarted: {
      writing = pending
      pending = ""
      write(writing + "\n")
    }
    onExited: {
      writing = ""
      if (pending.length) running = true
      else root.historyDirty = false
    }
  }
  Timer {
    interval: 1000
    running: true
    repeat: true
    onTriggered: { if (!root.historyDirty && !historyRead.running) historyRead.running = true }
  }
  Process {
    id: bootProc
    command: ["cat", "/proc/sys/kernel/random/boot_id"]
    stdout: StdioCollector { onStreamFinished: { root.bootId = text.trim(); initializeProc.running = true } }
  }
  Process {
    id: initializeProc
    command: [root.pluginDir + "/initialize-history.sh"]
    onExited: { historyRead.running = true; currentProc.running = true; textWatcher.running = true; imageWatcher.running = true }
  }
  Process {
    id: currentProc
    command: [root.pluginDir + "/capture.sh"]
    stdout: StdioCollector { onStreamFinished: root.addEntry(text) }
  }
  Process {
    id: textWatcher
    command: ["setpriv", "--pdeathsig", "TERM", "wl-paste", "--type", "text", "--watch", root.pluginDir + "/capture.sh", "text"]
    stdout: SplitParser { onRead: function(data) { root.addEntry(data) } }
    onExited: restartTimer.restart()
  }
  Process {
    id: imageWatcher
    command: ["setpriv", "--pdeathsig", "TERM", "wl-paste", "--type", "image/png", "--watch", root.pluginDir + "/capture.sh", "image/png"]
    stdout: SplitParser { onRead: function(data) { root.addEntry(data) } }
    onExited: restartTimer.restart()
  }
  Timer {
    id: restartTimer
    interval: 1000
    onTriggered: { if (!textWatcher.running) textWatcher.running = true; if (!imageWatcher.running) imageWatcher.running = true }
  }
  Process {
    id: copyProc
    property string payload: ""
    stdinEnabled: true
    onStarted: {
      write(payload + "\n")
      payload = ""
    }
  }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "io.github.krishang-zinzuwadia.omarchy-clipboard"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    MouseArea { anchors.fill: parent; onClicked: root.close() }
    BorderSurface {
      id: card
      width: Math.min(360, panel.width - 32)
      height: Math.min(330, panel.height - 32)
      anchors.centerIn: parent
      color: root.background
      borderSpec: Border.surfaceSpec("menu", "border", root.border, 1)
      radius: 0
      padding: Style.space(8)
      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        id: keyboard
        anchors.fill: parent
        focus: true
        Keys.onPressed: function(event) {
          if (root.deleteConfirmation) {
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) root.removeCurrent()
            else if (event.key === Qt.Key_Escape) root.deleteConfirmation = false
            event.accepted = true; return
          }
          if (event.key === Qt.Key_Escape) { root.filterText ? (root.filterText = "", root.rebuild()) : root.close() }
          else if (event.key === Qt.Key_Up || event.key === Qt.Key_Left) root.move(-1)
          else if (event.key === Qt.Key_Down || event.key === Qt.Key_Right) root.move(1)
          else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) root.copy(root.selectedIndex)
          else if (event.key === Qt.Key_P) root.togglePin(root.selectedIndex)
          else if (event.key === Qt.Key_Delete) root.deleteCurrent()
          else if (event.key === Qt.Key_Backspace && root.filterText.length) { root.filterText = root.filterText.slice(0, -1); root.selectedIndex = 0; root.rebuild() }
          else if (event.modifiers & (Qt.MetaModifier | Qt.ControlModifier | Qt.AltModifier)) {}
          else if (event.text && event.text.length === 1 && event.text.charCodeAt(0) >= 32) { root.filterText += event.text; root.selectedIndex = 0; root.rebuild() }
          else return
          event.accepted = true
        }
      }
      Item {
        anchors.fill: parent
        anchors.margins: card.contentLeftInset
        ListView {
          id: list
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.top: parent.top
          anchors.bottom: footer.top
          model: model; currentIndex: root.selectedIndex; clip: true; spacing: 0
          boundsBehavior: Flickable.StopAtBounds
          highlightFollowsCurrentItem: true
          highlight: Rectangle {
            width: list.width
            height: 78
            color: "#584e51"
            border.width: 2
            border.color: "#b59790"
          }
          Behavior on contentY { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
          delegate: Rectangle {
            id: row
            required property int index
            required property int historyIndex
            required property string kind
            required property string entryText
            required property string path
            required property bool pinned
            width: list.width; height: 78; radius: 0
            color: "transparent"
            border.width: 0
            border.color: "#b59790"
            Rectangle {
              anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
              height: 1; color: root.border; opacity: 0.55
            }
            Row {
              anchors.fill: parent; anchors.margins: 10; spacing: 10
              Image { width: kind === "image" ? 62 : 0; height: parent.height; source: path ? "file://" + path : ""; fillMode: Image.PreserveAspectFit; asynchronous: true; smooth: true }
              Column {
                width: parent.width - (kind === "image" ? 72 : 0); anchors.verticalCenter: parent.verticalCenter; spacing: 3
                Text { text: pinned ? "● PINNED" : (kind === "image" ? "IMAGE" : "TEXT"); color: row.pinned ? "#ebcb8b" : root.foreground; opacity: .7; font.pixelSize: 11 }
                Text { width: parent.width; text: kind === "image" ? "Image clipboard item" : entryText.replace(/\s+/g, " "); textFormat: Text.PlainText; color: root.foreground; elide: Text.ElideRight; font.pixelSize: Style.font.title }
              }
            }
            MouseArea {
              anchors.fill: parent
              onClicked: root.copy(row.index)
            }
          }
          Text { anchors.centerIn: parent; visible: model.count === 0; text: root.history.length ? "No matching clipboard items" : "Clipboard is empty"; color: root.foreground; opacity: .7; font.pixelSize: Style.font.title }
        }
        Text {
          id: footer
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          height: Style.space(22)
          text: root.filterText.length ? root.filterText : "↑ ↓ ← → navigate    Enter select    P pin    Delete remove    Esc close"
          color: root.foreground; opacity: 0.55; elide: Text.ElideRight; textFormat: Text.PlainText
          font.family: Style.font.menuFamily; font.pixelSize: Style.font.caption
          verticalAlignment: Text.AlignVCenter
        }
      }
      Rectangle {
        visible: root.deleteConfirmation; anchors.fill: parent; radius: 0; color: root.background
        Column {
          anchors.centerIn: parent; width: Math.min(parent.width - 40, 400); spacing: 14
          Text { width: parent.width; text: "Delete pinned clipboard item?"; wrapMode: Text.Wrap; color: root.foreground; font.pixelSize: Style.font.heading; horizontalAlignment: Text.AlignHCenter }
          Text { width: parent.width; text: "This item is saved across reboots. Enter deletes; Esc cancels."; wrapMode: Text.Wrap; color: root.foreground; opacity: .75; horizontalAlignment: Text.AlignHCenter }
        }
      }
    }
  }
}
