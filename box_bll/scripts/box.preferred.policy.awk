# Shared candidate policy. TSV ledgers contain URI-encoded node names, never code.
function read_inventory(    line,a) {
    while ((getline line < (work "/inventory")) > 0) {
        if (split(line,a,"\t") != 3) continue
        present[a[1]] = 1; alive[a[1]] = a[2]; latency[a[1]] = a[3]
    }
    while ((getline line < (work "/members")) > 0) {
        if (split(line,a,"\t") != 2) continue
        scoped[a[1]] = 1; selectable[a[1],a[2]] = 1
    }
}
function read_state(    line,a,i,fields) {
    while ((getline line < (state "/nodes")) > 0) {
        fields = split(line,a,"\t")
        if (fields != 8 && fields != 9) continue
        for (i = 2; i <= 9; i++) node[a[1],i] = a[i]
        if (fields == 8) node[a[1],9] = "ipqs"
        known[a[1]] = 1
    }
    while ((getline line < (state "/" ip_ledger)) > 0) {
        if (split(line,a,"\t") != 5) continue
        for (i = 2; i <= 5; i++) ip[a[1],i] = a[i]
    }
    while ((getline line < (state "/health")) > 0) {
        if (split(line,a,"\t") != 3) continue
        failures[a[1]] = a[2]; health_at[a[1]] = a[3]
    }
    while ((getline line < (state "/choices")) > 0) {
        if (split(line,a,"\t") != 4) continue
        chosen[a[1]] = a[2]; chosen_cc[a[1]] = a[3]
    }
    if (keyless) while ((getline line < (state "/retry.proxycheck-exits")) > 0) {
        if (split(line,a,"\t") == 3) exit_retry[a[1]] = a[2] + 0
    }
}
function missing_report(name,    v4,v6) {
    v4 = node[name,3]; v6 = node[name,4]
    return !ip[v4,2] || (v6 != "" && v6 != "-" && !ip[v6,2])
}
function eligible(name, scope,    v4,v6,c6,r6,at6) {
    if (!present[name] || !known[name] || node[name,2] + 0 <= 0 || node[name,2] > now || failures[name] >= 3) return 0
    if (scoped[scope] && !selectable[scope,name]) return 0
    v4 = node[name,3]; v6 = node[name,4]
    cc = ip[v4,3]; risk = ip[v4,4]; report_at = ip[v4,2] + 0
    if (cc !~ /^[A-Z][A-Z]$/ || report_at <= 0 || report_at > now || ip[v4,5] != "0" || risk > maxrisk) return 0
    if (v6 != "-") {
        c6 = ip[v6,3]; r6 = ip[v6,4]; at6 = ip[v6,2] + 0
        if (c6 != cc || at6 <= 0 || at6 > now || ip[v6,5] != "0" || r6 > maxrisk) return 0
        if (r6 > risk) risk = r6
        if (at6 < report_at) report_at = at6
    }
    if (scope == "OTHER" && cc ~ /^(SG|HK|JP|US|TW)$/) return 0
    if (scope != "ALL" && scope != "OTHER" && scope != cc) return 0
    if ((scope == "ALL" || scope == "OTHER") && !allow_country_change && chosen_cc[scope] != "" && chosen_cc[scope] != cc) return 0
    delay = latency[name] > 0 ? latency[name] : node[name,8]
    if (delay + 0 <= 0) delay = 999999
    return 1
}
function add_job(name, priority, interval,    v4,v6,due) {
    if (!present[name] || jobs[name] || name == reject) return
    # Avoid repeating failed echo/lookup attempts on every local polling tick.
    if (known[name] && node[name,9] == provider && now - node[name,7] < 900 && node[name,7] >= requested) return
    v4 = node[name,3]; v6 = node[name,4]
    if (priority > 0 && keyless && exit_retry[v4] > now) return
    due = !known[name] || now - node[name,2] >= interval || now - ip[v4,2] >= review
    if (v6 != "-" && v6 != "" && now - ip[v6,2] >= review) due = 1
    if (priority >= 2) due = !known[name] || node[name,9] != provider || missing_report(name) || node[name,7] < requested || now - node[name,7] >= review
    if (due) { jobs[name] = 1; print priority "\t" (node[name,7] + 0) "\t" name }
}
BEGIN {
    state = ENVIRON["PREFERRED_STATE"]; work = ENVIRON["PREFERRED_WORK"]
    ip_ledger = ENVIRON["PREFERRED_IP_LEDGER"] != "" ? ENVIRON["PREFERRED_IP_LEDGER"] : "ips"
    provider = ENVIRON["PREFERRED_REPUTATION_PROVIDER"] != "" ? ENVIRON["PREFERRED_REPUTATION_PROVIDER"] : "ipqs"
    keyless = ENVIRON["PREFERRED_KEYLESS"] == "true"
    now = ENVIRON["PREFERRED_NOW"] + 0; maxrisk = ENVIRON["PREFERRED_MAX_RISK"] + 0
    allow_country_change = ENVIRON["PREFERRED_ALLOW_COUNTRY_CHANGE"] == "true"
    action = ENVIRON["PREFERRED_ACTION"]; scope = ENVIRON["PREFERRED_SCOPE"]
    reject = ENVIRON["PREFERRED_REJECT"]
    read_inventory(); read_state()
    if (action == "rank") {
        for (name in present) if (eligible(name, scope) && delay < 999999)
            print name "\t" int(risk / 25) "\t" (node[name,5] + 0) "\t" delay "\t" cc "\t" risk "\t" report_at "\t" node[name,2]
    } else if (action == "verdict") {
        name = ENVIRON["PREFERRED_VALUE"]
        if (eligible(name, scope)) print cc "\t" risk "\t" report_at "\t" node[name,2]
    } else if (action == "latency") {
        name = ENVIRON["PREFERRED_VALUE"]
        d = latency[name] > 0 ? latency[name] : node[name,8]
        if (d > 0) print d
    } else if (action == "jobs") {
        review = ENVIRON["PREFERRED_REVIEW_INTERVAL"] + 0
        exit_interval = ENVIRON["PREFERRED_EXIT_INTERVAL"] + 0
        backups = ENVIRON["PREFERRED_BACKUPS"] + 0
        requested = ENVIRON["PREFERRED_SCAN_REQUEST"] + 0
        while ((getline line < (work "/groups")) > 0) {
            split(line,a,"\t"); scope = a[1]
            if (a[4] != 1) continue
            used = 1
            current = a[3] == reject ? chosen[scope] : a[3]
            add_job(current, 0, exit_interval)
            found = 0; nbackup = 0
            while ((getline row < (work "/" scope ".rank")) > 0) {
                split(row,b,"\t"); found = 1
                if (b[1] == current) continue
                if (nbackup++ >= backups) break
                add_job(b[1], 1, review)
            }
            close(work "/" scope ".rank")
            if (!found) empty_pool = 1
        }
        if (used || requested) {
            for (name in present) {
                if (!known[name] || node[name,9] != provider || missing_report(name) || (requested && node[name,7] < requested)) add_job(name, 2, review)
                else if (empty_pool && now - node[name,7] >= review) add_job(name, 3, review)
            }
        }
    } else if (action == "health") {
        while ((getline line < (work "/groups")) > 0) {
            split(line,a,"\t"); name = a[3]
            if (a[4] != 1 || !present[name] || seen[name]++) continue
            if (alive[name] == 1) {
                if (failures[name] > 0) print name "\t0\t" now
            } else if (now - health_at[name] >= 300) print name "\t" (failures[name] + 1) "\t" now
        }
    } else if (action == "status") {
        print "Node\tIPv4\tIPv6\tCountry\tRisk IPv4\tRisk IPv6\tDelay ms\tReputation time IPv4\tReputation time IPv6\tExit time\tIP changes\tReputation source"
        for (name in present) {
            v4 = node[name,3]; v6 = node[name,4]
            d = latency[name] > 0 ? latency[name] : node[name,8]
            print name "\t" v4 "\t" v6 "\t" ip[v4,3] "\t" ip[v4,4] "\t" ip[v6,4] "\t" (d > 0 ? d : "-") "\t" ip[v4,2] "\t" ip[v6,2] "\t" node[name,2] "\t" (node[name,5] + 0) "\t" provider
        }
    } else { print "unknown policy action" > "/dev/stderr"; exit 2 }
}
