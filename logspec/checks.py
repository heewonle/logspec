"""설계서 → 검사 목록. 검사 하나는 '위반 행을 돌려주는 SQL' 하나다.

category  schema / field / business / sequence / duplicate / volume / drift
judgment  auto  = 위반이면 곧 이슈 (타입·null·허용값·범위·참조·순서)
          human = 사람이 해석해야 함 (볼륨·분포 변화는 점검·이벤트·패치일 수도 있다)
"""
from dataclasses import dataclass

from .spec import TableSpec

DUCK_TYPES = {
    "int": {"BIGINT", "INTEGER", "SMALLINT", "TINYINT", "HUGEINT", "UBIGINT", "UINTEGER", "USMALLINT", "UTINYINT"},
    "float": {"FLOAT", "DOUBLE", "REAL", "DECIMAL"},
    "string": {"VARCHAR"}, "enum": {"VARCHAR"}, "bool": {"BOOLEAN"},
    "timestamp": {"TIMESTAMP", "TIMESTAMP_NS", "TIMESTAMP_MS", "TIMESTAMP_S", "TIMESTAMP WITH TIME ZONE", "DATE"},
}


@dataclass
class Check:
    id: str
    table: str
    field: str | None
    kind: str
    category: str
    description: str
    sql: str | None = None          # 위반 행을 돌려주는 SELECT
    count_sql: str | None = None    # 위반 수 하나만 돌려주는 SELECT
    severity: str = "error"
    judgment: str = "auto"
    needs: tuple = ()               # 이 검사가 쓰는 컬럼 (없으면 실행 불가로 표시)


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def lit(v) -> str:
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return str(v)


def build_checks(spec: TableSpec, period: tuple | None) -> list[Check]:
    t, T = spec.table, q(spec.table)
    out = []
    add = out.append
    for name, f in spec.fields.items():
        c = q(name)
        base = f"{t}.{name}"
        if f.get("not_null"):
            add(Check(f"{base}:not_null", t, name, "not_null", "field", "값이 비어 있으면 안 됨",
                      f"SELECT * FROM {T} WHERE {c} IS NULL", needs=(name,)))
        if f.get("unique"):
            add(Check(f"{base}:unique", t, name, "unique", "duplicate", "값이 중복되면 안 됨",
                      f"SELECT * FROM {T} WHERE {c} IN (SELECT {c} FROM {T} GROUP BY 1 HAVING count(*) > 1)",
                      needs=(name,)))
        if f.get("values"):
            vals = ", ".join(lit(v) for v in f["values"])
            add(Check(f"{base}:enum", t, name, "enum", "field", f"허용값 {f['values']} 밖",
                      f"SELECT * FROM {T} WHERE {c} IS NOT NULL AND {c} NOT IN ({vals})", needs=(name,)))
        if "min" in f:
            add(Check(f"{base}:min", t, name, "range", "field", f"{f['min']} 이상이어야 함",
                      f"SELECT * FROM {T} WHERE {c} < {lit(f['min'])}", needs=(name,)))
        if "max" in f:
            add(Check(f"{base}:max", t, name, "range", "field", f"{f['max']} 이하여야 함",
                      f"SELECT * FROM {T} WHERE {c} > {lit(f['max'])}", needs=(name,)))
        if f.get("pattern"):
            add(Check(f"{base}:pattern", t, name, "pattern", "field", f"형식 {f['pattern']}",
                      f"SELECT * FROM {T} WHERE {c} IS NOT NULL AND NOT regexp_full_match({c}::VARCHAR, {lit(f['pattern'])})",
                      needs=(name,)))
        if f.get("fk"):
            rt, rc = f["fk"].split(".")
            add(Check(f"{base}:fk", t, name, "fk", "field", f"{f['fk']} 에 있어야 함",
                      f"SELECT * FROM {T} WHERE {c} IS NOT NULL AND {c} NOT IN (SELECT {q(rc)} FROM {q(rt)})",
                      needs=(name,)))
        if f.get("not_equal"):
            o = f["not_equal"]
            add(Check(f"{base}:not_equal", t, name, "not_equal", "business", f"{o} 와 같으면 안 됨",
                      f"SELECT * FROM {T} WHERE {c} = {q(o)}", needs=(name, o)))
        if f.get("within_period") and period:
            add(Check(f"{base}:period", t, name, "period", "sequence",
                      f"적재 기간 [{period[0]}, {period[1]}) 안이어야 함",
                      f"SELECT * FROM {T} WHERE {c} < TIMESTAMP {lit(period[0])} OR {c} >= TIMESTAMP {lit(period[1])}",
                      needs=(name,)))

    if len(spec.key) > 1:
        cols = ", ".join(q(k) for k in spec.key)
        add(Check(f"{t}:key", t, None, "unique", "duplicate", f"키 ({', '.join(spec.key)}) 중복 금지",
                  f"SELECT {T}.* FROM {T} JOIN (SELECT {cols} FROM {T} GROUP BY ALL HAVING count(*) > 1) d USING ({cols})",
                  needs=tuple(spec.key)))
    if spec.duplicates:
        cols = ", ".join(q(k) for k in spec.duplicates)
        add(Check(f"{t}:duplicate_rows", t, None, "duplicate", "duplicate",
                  f"({', '.join(spec.duplicates)}) 가 같은 행이 두 번 적재되면 안 됨",
                  f"SELECT {T}.* FROM {T} JOIN (SELECT {cols} FROM {T} GROUP BY ALL HAVING count(*) > 1) d USING ({cols})",
                  needs=tuple(spec.duplicates)))

    for r in spec.rules:
        cid = f"{t}:rule:{r['name']}"
        sev, jud = r.get("severity", "error"), r.get("judgment", "auto")
        desc = r.get("description", r["name"])
        cat = "sequence" if any(w in r["name"] for w in ("after", "within", "overlap", "order")) else "business"
        if "row" in r:
            add(Check(cid, t, None, "rule_row", cat, desc,
                      f"SELECT * FROM {T} WHERE NOT coalesce(({r['row']}), false)", severity=sev, judgment=jud))
        elif "violations" in r:
            add(Check(cid, t, None, "rule_sql", cat, desc, r["violations"], severity=sev, judgment=jud))
        elif "count" in r:
            add(Check(cid, t, None, "rule_count", cat, desc, count_sql=r["count"], severity=sev, judgment=jud))
        elif "running_balance" in r:
            rb = r["running_balance"]
            p, o, d, b = (q(rb[k]) for k in ("partition", "order", "delta", "balance"))
            add(Check(cid, t, None, "running_balance", "business", desc,
                      f"SELECT * FROM (SELECT *, lag({b}) OVER (PARTITION BY {p} ORDER BY {o}) AS _prev FROM {T}) "
                      f"WHERE _prev IS NOT NULL AND {b} <> _prev + {d}",
                      severity=sev, judgment=jud, needs=tuple(rb[k] for k in ("partition", "order", "delta", "balance"))))

    tf = spec.time_field
    if spec.volume and tf and period:
        lo, hi = spec.volume["daily_ratio_vs_median7"]
        tq = q(tf)
        add(Check(f"{t}:volume", t, tf, "volume", "volume",
                  f"일별 행 수가 기간 중앙값의 {lo}~{hi}배 안 (빈 날 포함)",
                  f"""WITH days AS (SELECT unnest(range(TIMESTAMP {lit(period[0])}, TIMESTAMP {lit(period[1])}, INTERVAL 1 DAY))::DATE AS day),
                     cnt AS (SELECT {tq}::DATE AS day, count(*) AS n FROM {T} GROUP BY 1),
                     d AS (SELECT days.day, coalesce(cnt.n, 0) AS n FROM days LEFT JOIN cnt USING (day)),
                     m AS (SELECT median(n) AS med FROM d)
                  SELECT d.day AS {tq}, d.n AS rows_on_day, round(m.med) AS median_rows, round(d.n / m.med, 3) AS ratio
                  FROM d, m WHERE d.n < {lo} * m.med OR d.n > {hi} * m.med ORDER BY 1""",
                  severity="warn", judgment="human", needs=(tf,)))
    for col in (spec.drift or {}).get("fields", []):
        psi_max = spec.drift.get("psi_max", 0.1)
        tq, cq = q(tf), q(col)
        add(Check(f"{t}.{col}:drift", t, col, "drift", "drift",
                  f"일별 {col} 분포가 기간 전체 분포와 PSI {psi_max} 이하",
                  f"""WITH x AS (SELECT {tq}::DATE AS day, coalesce({cq}::VARCHAR, '∅') AS v FROM {T}
                              {f"WHERE {tq} >= TIMESTAMP {lit(period[0])} AND {tq} < TIMESTAMP {lit(period[1])}" if period else ""}),
                     dd AS (SELECT day, v, count(*)::DOUBLE / sum(count(*)) OVER (PARTITION BY day) AS p FROM x GROUP BY 1, 2),
                     base AS (SELECT v, count(*)::DOUBLE / sum(count(*)) OVER () AS p0 FROM x GROUP BY 1),
                     grid AS (SELECT DISTINCT day FROM x),
                     j AS (SELECT g.day, b.v, coalesce(dd.p, 0) AS p, b.p0 FROM grid g CROSS JOIN base b
                           LEFT JOIN dd ON dd.day = g.day AND dd.v = b.v
                           UNION ALL SELECT dd.day, dd.v, dd.p, 0 FROM dd WHERE dd.v NOT IN (SELECT v FROM base)),
                     psi AS (SELECT day, sum((greatest(p, 1e-4) - greatest(p0, 1e-4)) * ln(greatest(p, 1e-4) / greatest(p0, 1e-4))) AS psi
                             FROM j GROUP BY 1)
                  SELECT day AS {tq}, round(psi, 4) AS psi FROM psi WHERE psi > {psi_max} ORDER BY 1""",
                  severity="warn", judgment="human", needs=(tf, col)))
    return out
