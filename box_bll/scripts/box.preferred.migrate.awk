# Targeted YAML migration for module-owned preferred groups, not a YAML serializer.
# Preserve other groups, subscription names, anchors, comments and scalar values.
# Block items and flow-mapping items are supported; ambiguous input is rejected.
BEGIN {
    n = split("ALL SG HK JP US TW OTHER", codes, " ")
    for (i = 1; i <= n; i++) owned["优选·" codes[i] "出口"] = 1
    owned["优选·探测出口"] = 1
    owned["优选·检测连接"] = 1
    list_indent = -1
}
function fail(message) {
    print "[preferred migration] " message > "/dev/stderr"
    failed = 1
    exit 2
}
function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }
function indent(s) { match(s, /^[ ]*/); return RLENGTH }
function unicode(s,    i,n,x) {
    n = 0
    for (i = 1; i <= length(s); i++) {
        x = index("0123456789abcdef", tolower(substr(s, i, 1))) - 1
        if (x < 0) return ""
        n = n * 16 + x
    }
    if (n < 1 || n > 65535 || (n >= 55296 && n <= 57343)) return ""
    if (n < 128) return sprintf("%c", n)
    if (n < 2048) return sprintf("%c%c", 192 + int(n / 64), 128 + n % 64)
    return sprintf("%c%c%c", 224 + int(n / 4096), 128 + int(n / 64) % 64, 128 + n % 64)
}
function scalar(s,    q,i,c,out,tail,digits) {
    s = trim(s); q = substr(s, 1, 1)
    if (q != "\"" && q != "'") {
        sub(/[[:space:]]+#.*/, "", s)
        return trim(s)
    }
    out = ""
    for (i = 2; i <= length(s); i++) {
        c = substr(s, i, 1)
        if (q == "'" && c == "'" && substr(s, i + 1, 1) == "'") { out = out "'"; i++; continue }
        if (q == "\"" && c == "\\") {
            c = substr(s, ++i, 1)
            if (c == "u" || c == "U") {
                digits = c == "u" ? 4 : 8
                c = unicode(substr(s, i + 1, digits)); i += digits
                if (c == "") return ""
            } else if (c != "\\" && c != "\"" && c != "/") return ""
        } else if (c == q) {
            tail = trim(substr(s, i + 1))
            return tail == "" || substr(tail, 1, 1) == "#" ? out : ""
        }
        out = out c
    }
    return ""
}
function property(s, key,    pattern) {
    pattern = "^[[:space:]]*(" key "|\"" key "\"|'" key "')[[:space:]]*:"
    if (!match(s, pattern)) return 0
    value_start = RLENGTH + 1
    return 1
}
function true_value(s) {
    sub(/[[:space:]]+#.*/, "", s)
    return trim(s) ~ /^(true|True|TRUE)$/
}
function flow(text,    open,i,c,q,escaped,depth,start,close_at,fields,part,name,flag,prefix,replacement) {
    delete flow_start; delete flow_end
    open = index(text, "{")
    if (!open) return text
    depth = 0; start = open + 1; fields = 0
    for (i = open; i <= length(text); i++) {
        c = substr(text, i, 1)
        if (q != "") {
            if (escaped) { escaped = 0; continue }
            if (q == "\"" && c == "\\") { escaped = 1; continue }
            if (q == "'" && c == "'" && substr(text, i + 1, 1) == "'") { i++; continue }
            if (c == q) q = ""
            continue
        }
        if (c == "\"" || c == "'") { q = c; continue }
        if (c == "#" && substr(text, i - 1, 1) ~ /[[:space:],\[{]/) {
            while (i <= length(text) && substr(text, i, 1) != "\n") i++
            continue
        }
        if (c == "{" || c == "[") depth++
        else if (c == "}" || c == "]") {
            depth--
            if (depth == 0) {
                flow_start[++fields] = start; flow_end[fields] = i - 1
                close_at = i; break
            }
        } else if (c == "," && depth == 1) {
            flow_start[++fields] = start; flow_end[fields] = i - 1
            start = i + 1
        }
    }
    if (!close_at) fail("unterminated flow group; original config retained")
    for (i = 1; i <= fields; i++) {
        part = substr(text, flow_start[i], flow_end[i] - flow_start[i] + 1)
        if (property(part, "name")) {
            if (name != "") fail("duplicate group name field")
            name = scalar(substr(part, value_start))
        } else if (property(part, "include-all-providers")) {
            if (flag) fail("duplicate include-all-providers field")
            flag = i
        }
    }
    if (!(name in owned)) return text
    if (seen[name]++) fail("duplicate preferred group")
    if (flag) {
        part = substr(text, flow_start[flag], flow_end[flag] - flow_start[flag] + 1)
        property(part, "include-all-providers")
        if (true_value(substr(part, value_start))) return text
        prefix = flow_start[flag] + value_start - 2
        return substr(text, 1, prefix) " true" substr(text, flow_end[flag] + 1)
    }
    part = trim(substr(text, flow_start[fields], flow_end[fields] - flow_start[fields] + 1))
    replacement = (part == "" ? " " : ", ") "include-all-providers: true"
    return substr(text, 1, close_at - 1) replacement substr(text, close_at)
}
function sequence(text, check_only,    open,i,c,q,escaped,depth,start,copied,out) {
    open = index(text, "["); copied = 1; depth = 0
    sequence_complete = 0
    for (i = open; i <= length(text); i++) {
        c = substr(text, i, 1)
        if (q != "") {
            if (escaped) { escaped = 0; continue }
            if (q == "\"" && c == "\\") { escaped = 1; continue }
            if (q == "'" && c == "'" && substr(text, i + 1, 1) == "'") { i++; continue }
            if (c == q) q = ""
            continue
        }
        if (c == "\"" || c == "'") { q = c; continue }
        if (c == "#" && substr(text, i - 1, 1) ~ /[[:space:],\[{]/) {
            while (i <= length(text) && substr(text, i, 1) != "\n") i++
            continue
        }
        if (c == "{" || c == "[") {
            if (depth == 1 && c == "{") start = i
            depth++
        } else if (c == "}" || c == "]") {
            depth--
            if (depth == 1 && c == "}" && start) {
                if (!check_only) out = out substr(text, copied, start - copied) flow(substr(text, start, i - start + 1))
                copied = i + 1; start = 0
            }
            if (depth == 0) {
                sequence_complete = 1
                return out substr(text, copied)
            }
        }
    }
    return ""
}
function flush(    i,s,body,field_indent,name,name_line,flag,pad,text,body_start) {
    if (!lines) return
    match(item[1], /^[ ]*-[ ]+/); body_start = RLENGTH + 1
    body = substr(item[1], body_start)
    if (body ~ /^(&[^[:space:]]+[[:space:]]+)?\{/) {
        text = item[1]
        for (i = 2; i <= lines; i++) text = text "\n" item[i]
        print flow(text)
    } else {
        field_indent = body_start - 1
        for (i = 1; i <= lines; i++) {
            if (i == 1) s = body
            else if (indent(item[i]) == field_indent) s = substr(item[i], field_indent + 1)
            else continue
            if (property(s, "name")) {
                if (name_line) fail("duplicate group name field")
                name = scalar(substr(s, value_start)); name_line = i
            } else if (property(s, "include-all-providers")) {
                if (flag) fail("duplicate include-all-providers field")
                flag = i
            }
        }
        if (name in owned) {
            if (seen[name]++) fail("duplicate preferred group")
            pad = sprintf("%" field_indent "s", "")
            for (i = 1; i <= lines; i++) {
                if (i == flag) {
                    s = i == 1 ? body : substr(item[i], field_indent + 1)
                    property(s, "include-all-providers")
                    if (true_value(substr(s, value_start))) print item[i]
                    else print (i == 1 ? substr(item[i], 1, body_start - 1) : pad) "include-all-providers: true"
                } else print item[i]
                if (i == name_line && !flag) print pad "include-all-providers: true"
            }
        } else for (i = 1; i <= lines; i++) print item[i]
    }
    delete item; lines = 0
}
{
    if (flow_sequence) {
        sequence_text = sequence_text "\n" $0
        # Defer patching until the complete sequence is present: flow() tracks
        # duplicate group names, so it must run only once for this sequence.
        sequence(sequence_text, 1)
        if (sequence_complete) {
            print sequence(sequence_text)
            flow_sequence = 0
        }
        next
    }
    if ($0 ~ /^(proxy-groups|"proxy-groups"|'proxy-groups')[[:space:]]*:/) {
        if (++sections > 1) fail("multiple proxy-groups sections")
        rest = $0; sub(/^[^:]+:/, "", rest)
        if (trim(rest) ~ /^\[/) {
            sequence($0, 1)
            if (sequence_complete) {
                print sequence($0)
            } else {
                flow_sequence = 1; sequence_text = $0
            }
            next
        }
        if (trim(rest) != "" && trim(rest) !~ /^#/) fail("unsupported proxy-groups declaration")
        in_groups = 1; print; next
    }
    if (!in_groups) { print; next }
    if ($0 ~ /^[^ #[:space:]-]/ || $0 ~ /^(---|\.\.\.)[[:space:]]*$/) {
        flush(); in_groups = 0; print; next
    }
    if ($0 ~ /^[ ]*-[ ]+/) {
        current_indent = indent($0)
        if (list_indent < 0) list_indent = current_indent
        if (current_indent == list_indent) {
            flush(); item[++lines] = $0; next
        }
    }
    if (lines) item[++lines] = $0
    else print
}
END {
    if (failed) exit 2
    if (flow_sequence) fail("unterminated proxy-groups sequence")
    flush()
}
