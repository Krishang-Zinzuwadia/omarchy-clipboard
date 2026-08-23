var MAX_ENTRIES = 300
var MAX_TEXT_CHARS = 16384
var MAX_STATE_BYTES = 4194304

function normalize(value) {
  if (!value || typeof value !== "object") return null
  var kind = String(value.kind || value.type || "")
  var pinned = Boolean(value.pinned)
  if (kind === "text") {
    var text = String(value.text || "")
    return text.length && text.length <= MAX_TEXT_CHARS ? { kind: "text", text: text, pinned: pinned, capturedAt: Number(value.capturedAt || value.time || Date.now()) } : null
  }
  if (kind === "image" && value.path) {
    var path = String(value.path)
    var mime = String(value.mime || "image/png")
    return path.length <= 4096 && mime.length <= 128 ? { kind: "image", path: path, mime: mime, pinned: pinned, capturedAt: Number(value.capturedAt || value.time || Date.now()) } : null
  }
  return null
}

function key(entry) {
  return entry.kind === "image" ? "image:" + entry.path : "text:" + entry.text
}

function estimatedBytes(entry) {
  // Three bytes per UTF-16 unit conservatively bounds UTF-8 text. JSON escaping
  // makes control characters larger in the serialized form, which JSON.stringify
  // includes in its character count.
  return JSON.stringify(entry).length * 3
}

function parseState(raw, bootId) {
  try {
    var source = String(raw || "{}")
    if (source.length > MAX_STATE_BYTES) return []
    var state = JSON.parse(source)
    var entries = Array.isArray(state) ? state : (state.items || [])
    if (!Array.isArray(entries) || entries.length > MAX_ENTRIES) return []
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
  var bytes = 64 + estimatedBytes(entry)
  limit = Math.min(Number(limit || MAX_ENTRIES), MAX_ENTRIES)
  for (var j = 0; j < old.length && next.length < limit; j++) {
    if (key(old[j]) === key(entry)) continue
    var candidateBytes = estimatedBytes(old[j])
    if (bytes + candidateBytes > MAX_STATE_BYTES) continue
    next.push(old[j])
    bytes += candidateBytes
  }
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
