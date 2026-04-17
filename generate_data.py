#!/usr/bin/env python3
"""
Gera data_creat.json e data_red.json e injeta DATA_CREAT/DATA_RED no index.html
com dados direto do JIRA (projetos CREAT e RED).
"""

import os
import json
import re
import base64
import requests
from datetime import date, datetime
from collections import Counter

# ── Credenciais ───────────────────────────────────────────────────────────────
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "d.chaves@g4educacao.com")
JIRA_TOKEN = os.environ.get("JIRA_TOKEN", "")
JIRA_BASE  = "https://g4educacao.atlassian.net/rest/api/3"

def jira_headers():
    creds = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_TOKEN}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Accept": "application/json", "Content-Type": "application/json"}

# ── Designers por time ────────────────────────────────────────────────────────
DESIGNERS_CREAT = ["Neemias Araujo do Amaral", "Flávia Lima", "Matheus Pio Nunes Gonçalves", "Vitor Santos Serodeo", "Pedro Marcondes", "David Chaves"]
DESIGNERS_RED   = ["Juliana Cespedes", "t.fonseca", "Sarah Vitorio", "Marcella Mancinelli"]

# Campos Jira → mapa de tipo de demanda via labels
STATUS_ATRASAVEIS = {"Enviada", "Na fila", "Em produção", "Revisão", "Alteração"}
STATUS_FINALIZADO = {"Finalizado"}
STATUS_CANCELADO  = {"Cancelado"}

# ── Buscar issues do Jira ─────────────────────────────────────────────────────
def fetch_all_issues(project):
    issues = []
    fields = ["summary", "status", "assignee", "duedate", "labels", "customfield_10125", "created", "resolutiondate", "issuetype"]
    next_token = None
    while True:
        body = {
            "jql": f"project = {project} AND created >= '2026-01-01' ORDER BY created DESC",
            "maxResults": 100,
            "fields": fields
        }
        if next_token:
            body["nextPageToken"] = next_token
        r = requests.post(f"{JIRA_BASE}/search/jql", headers=jira_headers(), json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        batch = data.get("issues", [])
        issues.extend(batch)
        next_token = data.get("nextPageToken")
        if not batch or not next_token or len(issues) >= 1000:
            break
    return issues

# ── Parsear issue ─────────────────────────────────────────────────────────────
def parse(issue):
    f       = issue["fields"]
    status  = f["status"]["name"]
    assignee = f.get("assignee")
    designer = assignee["displayName"] if assignee else ""
    labels  = f.get("labels") or []
    bu      = f.get("customfield_10125") or ""
    prazo   = f.get("duedate") or ""
    criado  = (f.get("created") or "")[:10]
    mes     = criado[:7]
    resol   = (f.get("resolutiondate") or "")[:10]
    hoje    = date.today().isoformat()

    # Tipo via labels (primeira label que não seja controle)
    tipo = "Sem categoria"
    control_labels = {"sem-capacidade", "prazo-invalido", "FREELA", "FREELANCER", "Freelancer"}
    for lbl in labels:
        if lbl not in control_labels:
            tipo = lbl
            break

    atrasado   = bool(prazo and prazo < hoje and status in STATUS_ATRASAVEIS)
    freelancer = "FREELANCER" in [l.upper() for l in labels]
    no_prazo = None
    if resol and prazo:
        no_prazo = resol <= prazo

    return {
        "titulo":       f.get("summary", "")[:60],
        "key":          issue["key"],
        "status":       status,
        "tipo":         tipo,
        "area":         bu,
        "designer":     designer,
        "prazo":        prazo,
        "entrega_real": resol,
        "criado":       criado,
        "mes":          mes,
        "atrasado":     atrasado,
        "freelancer":   freelancer,
        "no_prazo":     no_prazo,
        "fora_sla":     False,  # calculado pelo SLA watcher
    }

# ── Construir summary ─────────────────────────────────────────────────────────
def build_summary(rows, designers):
    hoje   = date.today().isoformat()
    total  = len(rows)

    atrasados   = [r for r in rows if r["atrasado"]]
    cancelados  = [r for r in rows if r["status"] in STATUS_CANCELADO]
    finalizados = [r for r in rows if r["status"] in STATUS_FINALIZADO]
    em_aprov    = [r for r in rows if r["status"] == "Aprovação pendente"]

    meses = sorted(set(r["mes"] for r in rows if r["mes"] and r["mes"] != "2026-02"), reverse=True)

    por_mes = {}
    for mes in meses:
        mr = [r for r in rows if r["mes"] == mes]
        ma = [r for r in mr if r["atrasado"]]
        mf = [r for r in mr if r["status"] in STATUS_FINALIZADO]
        mc = [r for r in mr if r["status"] in STATUS_CANCELADO]
        por_mes[mes] = {
            "total":        len(mr),
            "atrasados":    len(ma),
            "finalizados":  len(mf),
            "cancelados":   len(mc),
            "fora_sla":     0,
            "freelancer":   sum(1 for r in mr if r["freelancer"]),
            "taxa_atraso":  round(len(ma)/len(mr)*100, 1) if mr else 0,
            "status_counts": dict(Counter(r["status"] for r in mr).most_common()),
            "tipo_counts":   dict(Counter(r["tipo"] for r in mr if r["tipo"]).most_common(8)),
            "area_counts":   dict(Counter(r["area"] for r in mr if r["area"]).most_common(8)),
            "area_atrasados":dict(Counter(r["area"] for r in ma if r["area"]).most_common(8)),
        }

    DISPLAY_NAME_MAP = {"David Chaves": "Freelancer"}

    designers_data = {}
    for designer in designers:
        dm   = [r for r in rows if r["designer"] == designer]
        da   = [r for r in dm if r["atrasado"]]
        df   = [r for r in dm if r["status"] in STATUS_FINALIZADO]
        dc   = [r for r in dm if r["status"] in STATUS_CANCELADO]
        dand = [r for r in dm if r["status"] in STATUS_ATRASAVEIS]

        designer_por_mes = {}
        for mes in meses:
            dmm  = [r for r in dm if r["mes"] == mes]
            dma  = [r for r in dmm if r["atrasado"]]
            dmf  = [r for r in dmm if r["status"] in STATUS_FINALIZADO]
            dmc  = [r for r in dmm if r["status"] in STATUS_CANCELADO]
            dmand = [r for r in dmm if r["status"] in STATUS_ATRASAVEIS]
            designer_por_mes[mes] = {
                "total":        len(dmm),
                "atrasadas":    len(dma),
                "finalizadas":  len(dmf),
                "canceladas":   len(dmc),
                "em_andamento": len(dmand),
                "freelancer":   sum(1 for r in dmm if r["freelancer"]),
            }

        display_name = DISPLAY_NAME_MAP.get(designer, designer)
        designers_data[display_name] = {
            "total":        len(dm),
            "em_andamento": len(dand),
            "finalizadas":  len(df),
            "atrasadas":    len(da),
            "canceladas":   len(dc),
            "fora_sla":     0,
            "freelancer":   sum(1 for r in dm if r["freelancer"]),
            "taxa_atraso":  round(len(da)/len(dm)*100, 1) if dm else 0,
            "tipos":        dict(Counter(r["tipo"] for r in dm if r["tipo"]).most_common(5)),
            "tipos_detalhes": {
                tipo: [{"titulo": r["titulo"], "key": r["key"]} for r in dm if r["tipo"] == tipo][:20]
                for tipo in list(dict(Counter(r["tipo"] for r in dm if r["tipo"]).most_common(5)).keys())
            },
            "areas":        dict(Counter(r["area"] for r in dm if r["area"]).most_common(3)),
            "por_mes":      designer_por_mes,
            "demandas_atrasadas": [
                {"titulo": r["titulo"], "prazo": r["prazo"], "status": r["status"], "area": r["area"]}
                for r in sorted(da, key=lambda x: x["prazo"])[:10]
            ],
        }

    # Métricas (campos não disponíveis no Jira — placeholder compatível)
    metricas = {
        "sla_medio_dias": None, "sla_amostras": 0, "sla_por_tipo": {},
        "taxa_pontualidade": None, "pont_amostras": 0,
        "taxa_aprov_1a": None, "aprov_1a_amostras": 0,
        "rev_medio": None, "rev_amostras": 0,
        "rating_medio": None, "rating_amostras": 0, "rating_dist": {},
    }

    freelancers = [r for r in rows if r["freelancer"]]

    return {
        "gerado_em":         hoje,
        "meses":             meses,
        "por_mes":           por_mes,
        "total":             total,
        "atrasados":         len(atrasados),
        "cancelados":        len(cancelados),
        "fora_sla":          0,
        "finalizados":       len(finalizados),
        "em_aprovacao":      len(em_aprov),
        "freelancer":        len(freelancers),
        "taxa_atraso_geral": round(len(atrasados)/total*100, 1) if total else 0,
        "status_counts":     dict(Counter(r["status"] for r in rows).most_common()),
        "tipo_counts":       dict(Counter(r["tipo"] for r in rows if r["tipo"]).most_common(8)),
        "area_counts":       dict(Counter(r["area"] for r in rows if r["area"]).most_common(8)),
        "area_atrasados":    dict(Counter(r["area"] for r in atrasados if r["area"]).most_common(8)),
        "demandas_atrasadas_por_area": {
            area: [
                {"titulo": r["titulo"], "key": r["key"], "prazo": r["prazo"], "status": r["status"], "designer": r["designer"]}
                for r in sorted(atrasados, key=lambda x: x["prazo"])
                if r["area"] == area
            ]
            for area in set(r["area"] for r in atrasados if r["area"])
        },
        "designers":         designers_data,
        "metricas":          metricas,
    }

# ── Injetar no index.html ─────────────────────────────────────────────────────
def inject_and_save(summary, team, index_path, data_path):
    with open(data_path, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  Salvo em {data_path}")

    with open(index_path) as f:
        html = f.read()

    data_js = json.dumps(summary, ensure_ascii=False)
    key = team.upper()
    html = re.sub(
        rf"const DATA_{key}\s*=\s*\{{.*?\}};",
        f"const DATA_{key} = {data_js};",
        html, flags=re.DOTALL
    )

    with open(index_path, "w") as f:
        f.write(html)
    print(f"  {index_path} — DATA_{key} atualizado")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not JIRA_TOKEN:
        print("ERRO: JIRA_TOKEN não definido.")
        exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    base = "." if os.path.exists("index.html") else script_dir
    index_path = os.path.join(base, "index.html")

    # ── CREAT ──
    print(f"\nBuscando dados do JIRA (projeto CREAT)...")
    issues_creat = fetch_all_issues("CREAT")
    print(f"  {len(issues_creat)} issues encontradas")
    rows_creat = [parse(i) for i in issues_creat]
    summary_creat = build_summary(rows_creat, DESIGNERS_CREAT)
    inject_and_save(summary_creat, "creat", index_path, os.path.join(base, "data_creat.json"))
    print(f"  CREAT: {summary_creat['total']} demandas | {summary_creat['atrasados']} atrasadas | {summary_creat['finalizados']} finalizadas")

    # ── RED ──
    print(f"\nBuscando dados do JIRA (projeto RED)...")
    issues_red = fetch_all_issues("RED")
    print(f"  {len(issues_red)} issues encontradas")
    rows_red = [parse(i) for i in issues_red]
    summary_red = build_summary(rows_red, DESIGNERS_RED)
    inject_and_save(summary_red, "red", index_path, os.path.join(base, "data_red.json"))
    print(f"  RED: {summary_red['total']} demandas | {summary_red['atrasados']} atrasadas | {summary_red['finalizados']} finalizadas")

    print(f"\nConcluído!")

if __name__ == "__main__":
    main()
