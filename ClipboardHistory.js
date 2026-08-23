function normalize(value) {
  if (!value || typeof value !== "object") return null
  var kind = String(value.kind || value.type || "")
  var pinned = Boolean(value.pinned)
  if (kind === "text") {
    var text = String(value.text || "")
    return text.length ? { kind: "text", text: text, pinned: pinned, capturedAt: Number(value.capturedAt || value.time || Date.now()) } : null
  }
  if (kind === "image" && value.path) {
    return { kind: "image", path: String(value.path), mime: String(value.mime || "image/png"), pinned: pinned, capturedAt: Number(value.capturedAt || value.time || Date.now()) }
  }
  return null
}

function key(entry) {
  return entry.kind === "image" ? "image:" + entry.path : "text:" + entry.text
}

function parseState(raw, bootId) {
  try {
    var state = JSON.parse(String(raw || "{}"))
    var entries = Array.isArray(state) ? state : (state.items || [])
    var sameBoot = Array.isArray(state) || !bootId || !state.bootId || state.bootId === bootId
    var next = []
    for (var i = 0; i < entries.length; i++) {
      var entry = normalize(entries[i])
      if (entry && (sameBoot || entry.pinned)) next.push(entry)
    }
    return next
  } catch (error) { return [] }
}

function add(history, value, limit) {
  var entry = normalize(value)
  if (!entry) return history
  var old = Array.isArray(history) ? history : []
  for (var i = 0; i < old.length; i++)
    if (key(old[i]) === key(entry)) entry.pinned = old[i].pinned
  var next = [entry]
  for (var j = 0; j < old.length && next.length < limit; j++)
    if (key(old[j]) !== key(entry)) next.push(old[j])
  return next
}

function ordered(history, filter) {
  var needle = String(filter || "").toLowerCase()
  var pinnedRows = []
  var regularRows = []
  for (var i = 0; i < history.length; i++) {
    var item = history[i]
    var haystack = item.kind === "image" ? "image " + item.mime : item.text
    if (needle && haystack.toLowerCase().indexOf(needle) < 0) continue
    var row = { entry: item, historyIndex: i }
    if (item.pinned) pinnedRows.push(row)
    else regularRows.push(row)
  }
  return pinnedRows.concat(regularRows)
}
