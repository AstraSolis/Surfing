# JSON and URI handling for box.preferred. Runs with BusyBox awk, LC_ALL=C.
# Small input windows avoid repeatedly scanning the entire response for each byte.
# Input is data only: no shell evaluation, jq, Python or downloaded script.
BEGIN {
    for (i = 1; i < 256; i++) ord[sprintf("%c", i)] = i
    action = ENVIRON["PREFERRED_ACTION"]
}
FNR == 1 && NR > 1 && action != "encode" { document(); input = "" }
{
    if (action == "encode") raw = raw (NR > 1 ? "\n" : "") $0
    else input = input $0 "\n"
}

function fail(message) {
    print "[preferred] " message > "/dev/stderr"
    failed = 1
    exit 2
}
function slice(start, size,    block,offset) {
    block = int((start - 1) / 2048)
    if (block != input_block) {
        input_buffer = substr(input, block * 2048 + 1, 2048)
        input_buffer_size = length(input_buffer)
        input_block = block
    }
    offset = start - block * 2048
    if (offset + size - 1 <= input_buffer_size) return substr(input_buffer, offset, size)
    return substr(input, start, size)
}
function ws() { while (pos <= input_size && slice(pos, 1) ~ /[ \t\r\n]/) pos++ }
function hex(s,    i,n,c) {
    n = 0
    for (i = 1; i <= length(s); i++) {
        c = index("0123456789abcdef", tolower(substr(s, i, 1))) - 1
        if (c < 0) fail("invalid hexadecimal escape")
        n = n * 16 + c
    }
    return n
}
function utf8(n) {
    if (n == 0) fail("NUL is unsupported")
    if (n < 128) return sprintf("%c", n)
    if (n < 2048) return sprintf("%c%c", 192 + int(n / 64), 128 + n % 64)
    if (n < 65536) return sprintf("%c%c%c", 224 + int(n / 4096), 128 + int(n / 64) % 64, 128 + n % 64)
    return sprintf("%c%c%c%c", 240 + int(n / 262144), 128 + int(n / 4096) % 64, 128 + int(n / 64) % 64, 128 + n % 64)
}
function string(    s,c,e,n,low) {
    if (slice(pos++, 1) != "\"") fail("expected JSON string")
    s = ""
    while (pos <= input_size) {
        c = slice(pos++, 1)
        if (c == "\"") return s
        if (c == "\\") {
            e = slice(pos++, 1)
            if (e == "\"" || e == "\\" || e == "/") c = e
            else if (e == "n") c = "\n"
            else if (e == "r") c = "\r"
            else if (e == "t") c = "\t"
            else if (e == "b") c = sprintf("%c", 8)
            else if (e == "f") c = sprintf("%c", 12)
            else if (e == "u") {
                if (length(slice(pos, 4)) != 4) fail("short Unicode escape")
                n = hex(slice(pos, 4)); pos += 4
                if (n >= 55296 && n <= 56319) {
                    if (slice(pos, 2) != "\\u") fail("unpaired Unicode surrogate")
                    pos += 2; low = hex(slice(pos, 4)); pos += 4
                    if (low < 56320 || low > 57343) fail("unpaired Unicode surrogate")
                    n = 65536 + (n - 55296) * 1024 + low - 56320
                } else if (n >= 56320 && n <= 57343) fail("unpaired Unicode surrogate")
                c = utf8(n)
            } else fail("invalid JSON escape")
        } else if (ord[c] < 32) fail("unescaped control character")
        s = s c
    }
    fail("unterminated JSON string")
}
function get(parent, key,    i,id) {
    for (i = 1; i <= count[parent]; i++) {
        id = child[parent, i]
        if (member[id] == key) return id
    }
    return 0
}
function parse(depth,    id,c,k,x,start) {
    if (depth > 64 || serial > 200000) fail("JSON limit exceeded")
    ws(); id = ++serial; c = slice(pos, 1)
    if (c == "{" || c == "[") {
        kind[id] = c == "{" ? "object" : "array"
        pos++; ws()
        if (slice(pos, 1) == (c == "{" ? "}" : "]")) { pos++; return id }
        while (1) {
            ws()
            if (c == "{") {
                k = string(); ws()
                if (get(id, k)) fail("duplicate JSON member")
                if (slice(pos++, 1) != ":") fail("expected colon")
            }
            x = parse(depth + 1)
            child[id, ++count[id]] = x
            if (c == "{") member[x] = k
            ws(); x = slice(pos++, 1)
            if (x == (c == "{" ? "}" : "]")) return id
            if (x != ",") fail("expected comma")
        }
    } else if (c == "\"") { kind[id] = "string"; value[id] = string() }
    else if (slice(pos, 4) == "true" || slice(pos, 5) == "false") {
        kind[id] = "boolean"; value[id] = slice(pos, 1) == "t" ? "true" : "false"
        pos += length(value[id])
    } else if (slice(pos, 4) == "null") { kind[id] = "null"; pos += 4 }
    else {
        start = slice(pos, 128)
        if (!match(start, /^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?/)) fail("invalid JSON value")
        kind[id] = "number"; value[id] = substr(start, 1, RLENGTH); pos += RLENGTH
    }
    return id
}
function document() {
    input_size = length(input); input_block = -1
    if (input_size > 4194304) fail("JSON document exceeds size limit")
    pos = 1; root = parse(0); ws()
    if (pos <= input_size || kind[root] != "object") fail("expected one JSON object")
    documents[++document_count] = root
}
function field(parent, name) { return value[get(parent, name)] }
function clean(s) { return s !~ /[\001-\037\177]/ }
function quote(s,    i,c,out) {
    out = "\""
    for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        if (c == "\\" || c == "\"") out = out "\\" c
        else if (ord[c] < 32) out = out sprintf("\\u%04x", ord[c])
        else out = out c
    }
    return out "\""
}
function encode(s,    i,c,out) {
    out = ""
    for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        out = out (c ~ /^[A-Za-z0-9_.~-]$/ ? c : sprintf("%%%02X", ord[c]))
    }
    return out
}
function decode(s,    i,c,out) {
    out = ""
    for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        if (c == "%") { c = utf8byte(substr(s, i + 1, 2)); i += 2 }
        out = out c
    }
    return out
}
function utf8byte(s) { if (length(s) != 2 || hex(s) == 0) fail("invalid URI escape"); return sprintf("%c", hex(s)) }
function intsetting(name, def, min, max,    id,n) {
    id = get(root, name)
    if (!id) return def
    n = value[id]
    if (kind[id] != "number" || n !~ /^[0-9]+$/ || n + 0 < min || n + 0 > max) fail("invalid setting: " name)
    return n + 0
}
function boolsetting(name, def,    id) {
    id = get(root, name)
    if (!id) return def
    if (kind[id] != "boolean") fail("invalid setting: " name)
    return value[id]
}
function textsetting(name, def,    id) {
    id = get(root, name)
    if (!id) return def
    if (kind[id] != "string" || !clean(value[id])) fail("invalid setting: " name)
    return value[id]
}
function ip4(s,    a,n,i,out) {
    n = split(s, a, ".")
    if (n != 4) return ""
    for (i = 1; i <= 4; i++) {
        if (a[i] !~ /^[0-9]+$/ || length(a[i]) > 3 || a[i] + 0 > 255) return ""
        out = out (i > 1 ? "." : "") (a[i] + 0)
    }
    # Only globally usable IPv4 addresses; documentation ranges remain useful in fixtures.
    if (a[1] == 0 || a[1] == 10 || a[1] == 127 || a[1] >= 224 ||
        (a[1] == 169 && a[2] == 254) || (a[1] == 172 && a[2] >= 16 && a[2] <= 31) ||
        (a[1] == 192 && a[2] == 168) || (a[1] == 100 && a[2] >= 64 && a[2] <= 127)) return ""
    return out
}
function ip6(s,    halves,a,b,n,m,i,out,part,dc) {
    s = tolower(s)
    if (s !~ /^[0-9a-f:]+$/ || length(s) > 39) return ""
    dc = split(s, halves, "::")
    if (dc > 2) return ""
    n = halves[1] == "" ? 0 : split(halves[1], a, ":")
    m = dc == 2 && halves[2] != "" ? split(halves[2], b, ":") : 0
    if ((dc == 1 && n != 8) || (dc == 2 && n + m >= 8)) return ""
    for (i = 1; i <= n; i++) if (length(a[i]) < 1 || length(a[i]) > 4) return ""
    for (i = 1; i <= m; i++) if (length(b[i]) < 1 || length(b[i]) > 4) return ""
    for (i = 1; i <= 8; i++) {
        part = i <= n ? a[i] : (i > 8 - m ? b[i - (8 - m)] : "0")
        out = out (i > 1 ? ":" : "") sprintf("%x", hex(part))
    }
    # Global unicast only. Mapped, local and link-local addresses are not exit evidence.
    if (out !~ /^[23][0-9a-f][0-9a-f][0-9a-f]:/) return ""
    return out
}
function mark(name, depth,    obj,t,all,i) {
    if (depth > 32 || visiting[name]) return
    visiting[name] = 1
    if (name in group_code) active[group_code[name]] = 1
    else {
        obj = get(proxies, name); t = field(obj, "type")
        if (t == "LoadBalance") {
            all = get(obj, "all")
            for (i = 1; i <= count[all]; i++) mark(value[child[all,i]], depth + 1)
        } else if (get(obj, "now")) mark(field(obj, "now"), depth + 1)
    }
    delete visiting[name]
}
function groups(    i,name,obj) {
    if (action == "snapshot") printf "%s", "" > (ENVIRON["PREFERRED_WORK"] "/groups")
    codes[1] = "ALL"; labels[1] = "ALL·优选"
    codes[2] = "SG"; labels[2] = "狮城地区·优选"
    codes[3] = "HK"; labels[3] = "香港地区·优选"
    codes[4] = "JP"; labels[4] = "日本地区·优选"
    codes[5] = "US"; labels[5] = "美国地区·优选"
    codes[6] = "TW"; labels[6] = "中国台湾·优选"
    codes[7] = "OTHER"; labels[7] = "其它地区·优选"
    for (i = 1; i <= 7; i++) group_code[labels[i]] = codes[i]
    proxies = get(root, "proxies")
    if (kind[proxies] != "object") fail("missing proxy registry")
    if (ENVIRON["PREFERRED_MODE"] == "global") mark("GLOBAL", 0)
    else if (ENVIRON["PREFERRED_MODE"] != "direct") {
        for (i = 1; i <= count[proxies]; i++) {
            obj = child[proxies,i]; name = member[obj]
            if (get(obj, "all") && name != "GLOBAL" && !(name in group_code) && name !~ /^优选·/)
                mark(name, 0)
        }
    }
    for (i = 1; i <= 7; i++) {
        name = "优选·" codes[i] "出口"; obj = get(proxies, name)
        if (kind[get(proxies, labels[i])] == "object" && field(obj, "type") == "Selector") {
            line = codes[i] "\t" encode(name) "\t" encode(field(obj, "now")) "\t" (active[codes[i]] ? 1 : 0)
            if (action == "snapshot") print line > (ENVIRON["PREFERRED_WORK"] "/groups")
            else print line
        }
    }
}
END {
    if (failed) exit 2
    if (action == "encode") { print encode(raw); exit }
    if (action == "decode") { print decode(ENVIRON["PREFERRED_VALUE"]); exit }
    if (action == "select") { print "{\"name\":" quote(decode(ENVIRON["PREFERRED_VALUE"])) "}"; exit }
    document(); root = documents[1]
    if (action == "settings") {
        print boolsetting("enabled", "false")
        controller = textsetting("controller", "http://127.0.0.1:9090")
        if (controller !~ /^http:\/\/127\.0\.0\.1:[0-9]+$/) fail("controller must use IPv4 loopback")
        split(controller, parts, ":")
        if (parts[3] + 0 < 1 || parts[3] + 0 > 65535) fail("invalid controller port")
        print controller
        print intsetting("probe_port", 7894, 1024, 65535)
        print intsetting("management_port", 7895, 1024, 65535)
        print boolsetting("check_ipv6", "true")
        print intsetting("review_interval", 86400, 3600, 604800)
        print intsetting("exit_interval", 3600, 900, 86400)
        print intsetting("selection_max_age", 3600, 300, 86400)
        print intsetting("daily_budget", 100, 1, 10000)
        print intsetting("request_gap", 5, 2, 60)
        print intsetting("batch_size", 5, 1, 30)
        print intsetting("backups", 2, 0, 3)
        print intsetting("max_risk", 74, 0, 89)
        print intsetting("poll_interval", 60, 30, 300)
        key = textsetting("api_key", "")
        print key != "" ? "true" : "false"
        print boolsetting("allow_country_change", "false")
    } else if (action == "providers") {
        list = get(root, "providers")
        if (!list) {
            print encode("1.主要地址"); print encode("2.备用地址"); print encode("3.额外地址")
        } else {
            if (kind[list] != "array" || count[list] < 1 || count[list] > 16) fail("invalid providers list")
            for (i = 1; i <= count[list]; i++) {
                item = child[list,i]; name = value[item]
                if (kind[item] != "string" || name == "" || name == "." || name == ".." || !clean(name) || length(name) > 256 || selected_providers[name]++)
                    fail("invalid or duplicate provider name")
                print encode(name)
            }
        }
    } else if (action == "controller-auth") {
        secret = textsetting("controller_secret", "")
        if (secret != "") print "header = " quote("Authorization: Bearer " secret)
    } else if (action == "ipqs-request") {
        key = textsetting("api_key", "")
        if (key == "") fail("API key is missing")
        print "url = " quote("https://ipqualityscore.com/api/json/ip/" encode(key) "/" encode(ENVIRON["PREFERRED_IP"]) "?strictness=0&allow_public_access_points=true")
    } else if (action == "ip") {
        s = field(root, "ip")
        s = ENVIRON["PREFERRED_FAMILY"] == "6" ? ip6(s) : ip4(s)
        if (s == "") fail("invalid exit IP")
        print s
    } else if (action == "score") {
        risk = get(root, "fraud_score"); abuse = get(root, "recent_abuse"); bot = get(root, "bot_status")
        cc = field(root, "country_code")
        if (kind[get(root, "success")] != "boolean" || field(root, "success") != "true" || kind[risk] != "number" || value[risk] + 0 < 0 || value[risk] + 0 > 100 ||
            kind[abuse] != "boolean" || kind[bot] != "boolean" || cc !~ /^[A-Z][A-Z]$/)
            fail("incomplete reputation response")
        print cc "\t" value[risk] "\t" (value[abuse] == "true" || value[bot] == "true" ? 1 : 0)
    } else if (action == "mode") {
        mode = tolower(field(root, "mode"))
        if (mode != "rule" && mode != "global" && mode != "direct") fail("unknown core mode")
        print mode
    } else if (action == "groups") groups()
    else if (action == "inventory" || action == "snapshot") {
        proxies = get(root, "proxies"); probe = get(proxies, "优选·探测出口"); all = get(probe, "all")
        if (field(probe, "type") != "Selector" || kind[all] != "array") fail("preferred probe group is missing")
        # Provider nodes are separate from GET /proxies in mihomo v1.19.33.
        for (i = 2; i <= document_count; i++) {
            list = get(documents[i], "proxies")
            if (kind[list] != "array") fail("invalid provider response")
            for (j = 1; j <= count[list]; j++) {
                obj = child[list,j]; name = field(obj, "name")
                provider_nodes[name] = obj; occurrences[name]++
            }
        }
        for (i = 1; i <= count[all]; i++) {
            name = value[child[all,i]]; obj = get(proxies, name)
            if (!obj) obj = provider_nodes[name]
            if (occurrences[name] > 1) continue
            t = tolower(field(obj, "type"))
            if (name == "" || !clean(name) || get(obj, "all") || t ~ /^(direct|reject|rejectdrop|pass|dns|rematch)$/ || !obj) continue
            history = get(obj, "history"); last = child[history,count[history]]
            delay = field(last, "delay") + 0
            samples = 0
            for (j = count[history]; j >= 1 && j > count[history] - 3; j--) {
                d = field(child[history,j], "delay") + 0
                if (d > 0) sample[++samples] = d
            }
            for (j = 1; j <= samples; j++) for (k = j + 1; k <= samples; k++)
                if (sample[j] > sample[k]) { d = sample[j]; sample[j] = sample[k]; sample[k] = d }
            if (samples > 0) delay = sample[int(samples / 2) + 1]
            print encode(name) "\t" (field(obj, "alive") == "false" ? 0 : 1) "\t" delay
        }
        if (action == "snapshot") groups()
    } else if (action == "delay") {
        delay = get(root, "delay")
        if (kind[delay] != "number" || value[delay] <= 0) fail("invalid delay")
        print value[delay] + 0
    } else fail("unknown JSON action")
}
