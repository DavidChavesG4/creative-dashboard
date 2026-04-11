#!/usr/bin/env python3
"""
Gera data_creat.json e data_red.json com dados dos bancos 2026 do Notion.
Roda pelo GitHub Actions e localmente para atualizar o dashboard.
"""

import os
import json
import re
import requests
from datetime import date
from collections import Counter

NOTION_TOKEN = os.environ["NOTION_TOKEN"]

# RED e CREAT são o mesmo banco — distinguidos pelo campo "Projeto JIRA" (select)
NOTION_DB_ID = "2e0b431349e180498fe0cbaf43c58f21"

TEAM_PROJETO = {
    "creat": "CREAT",
    "red":   "RED",
}

# Demandas consideradas atrasadas quando prazo < hoje e estão nesses status
STATUS_ATRASAVEIS = {"Enviado", "Na fila", "Em produção", "Revisão", "Alteração"}

# Designers fixos por time — nomes exatamente como aparecem no Notion
DESIGNERS = {
    "creat": ["Flávia Lima", "Neemias Amaral", "Pedro Marcondes", "Vitor Santos Serodeo", "Matheus Gonçalves"],
    "red":   ["Flávia Lima", "Neemias Amaral", "Pedro Marcondes", "Vitor Santos Serodeo", "Matheus Gonçalves", "Juliana Cespedes"],
}

# Variações de nome aceitas (Notion pode ter nome levemente diferente)
NAME_MAP = {
    "Vitor Serodeo":        "Vitor Santos Serodeo",
    "Vitor Santos Serodeo": "Vitor Santos Serodeo",
    "Neemias":              "Neemias Amaral",
    "Flavia Lima":          "Flávia Lima",
    "Matheus Goncalves":    "Matheus Gonçalves",
}

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def fetch_all(db_id):
    results, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=HEADERS, json=body
        )
        r.raise_for_status()
        data = r.json()
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results


def parse(page):
    props = page.get("properties", {})

    def txt(k):
        arr = props.get(k, {}).get("rich_text", [])
        return arr[0].get("plain_text", "") if arr else ""

    def sel(k):
        s = props.get(k, {}).get("select", {})
        return s.get("name", "") if s else ""

    def status():
        s = props.get("Status", {}).get("status", {})
        return s.get("name", "") if s else ""

    def dt(k):
        d = props.get(k, {}).get("date", {})
        return d.get("start", "") if d else ""

    def people(k):
        arr = props.get(k, {}).get("people", [])
        name = arr[0].get("name", "") if arr else ""
        return NAME_MAP.get(name, name)

    def chk(k):
        return props.get(k, {}).get("checkbox", False)

    def ttl():
        for key in ["", "Nome", "Name"]:
            arr = props.get(key, {}).get("title", [])
            if arr:
                return arr[0].get("plain_text", "")
        return ""

    prazo = dt("📅 Prazo entrega")
    st    = status()
    hoje  = date.today().isoformat()
    tipo  = sel("Tipo de Demanda").replace("?: ", "").strip() or "Sem categoria"

    return {
        "titulo":     ttl(),
        "status":     st,
        "tipo":       tipo,
        "area":       txt("Área Solicitante"),
        "solicitante":txt("Solicitante"),
        "designer":   people("Creative"),
        "freelancer": txt("Freelancer"),
        "prazo":      prazo,
        "criado":     page.get("created_time", "")[:10],
        "mes":        page.get("created_time", "")[:7],  # "2026-04"
        "prioridade": sel("Prioridade"),
        "projeto":    sel("Projeto JIRA"),
        "fora_sla":   chk("⚠ Fora de SLA?"),
        "atrasado":   bool(prazo and prazo < hoje and st in STATUS_ATRASAVEIS),
    }


def build_summary(rows, team):
    hoje  = date.today().isoformat()
    total = len(rows)

    atrasados   = [r for r in rows if r["atrasado"]]
    cancelados  = [r for r in rows if r["status"] == "Cancelada"]
    fora_sla    = [r for r in rows if r["fora_sla"]]
    finalizados = [r for r in rows if r["status"] in ["Finalizado", "Aprovado"]]
    em_aprovacao = [r for r in rows if r["status"] == "Aprovação pendente"]

    # Meses disponíveis
    meses = sorted(set(r["mes"] for r in rows if r["mes"]), reverse=True)

    # Resumo por mês
    por_mes = {}
    for mes in meses:
        mr = [r for r in rows if r["mes"] == mes]
        ma = [r for r in mr if r["atrasado"]]
        mf = [r for r in mr if r["status"] in ["Finalizado", "Aprovado"]]
        mc = [r for r in mr if r["status"] == "Cancelada"]
        ms_sla = [r for r in mr if r["fora_sla"]]
        por_mes[mes] = {
            "total":      len(mr),
            "atrasados":  len(ma),
            "finalizados":len(mf),
            "cancelados": len(mc),
            "fora_sla":   len(ms_sla),
            "taxa_atraso":round(len(ma)/len(mr)*100, 1) if mr else 0,
            "status_counts": dict(Counter(r["status"] for r in mr).most_common()),
            "tipo_counts":   dict(Counter(r["tipo"] for r in mr if r["tipo"]).most_common(8)),
            "area_counts":   dict(Counter(r["area"] for r in mr if r["area"]).most_common(8)),
            "area_atrasados":dict(Counter(r["area"] for r in ma if r["area"]).most_common(8)),
        }

    designers_data = {}
    for designer in DESIGNERS[team]:
        dm   = [r for r in rows if r["designer"] == designer]
        da   = [r for r in dm if r["atrasado"]]
        df   = [r for r in dm if r["status"] in ["Finalizado", "Aprovado"]]
        dc   = [r for r in dm if r["status"] == "Cancelada"]
        ds   = [r for r in dm if r["fora_sla"]]
        dand = [r for r in dm if r["status"] in ["Na fila", "Em produção", "Enviado", "Alteração", "Revisão"]]

        # Por mês do designer
        designer_por_mes = {}
        for mes in meses:
            dmm = [r for r in dm if r["mes"] == mes]
            dma = [r for r in dmm if r["atrasado"]]
            designer_por_mes[mes] = {
                "total":     len(dmm),
                "atrasadas": len(dma),
            }

        designers_data[designer] = {
            "total":        len(dm),
            "em_andamento": len(dand),
            "finalizadas":  len(df),
            "atrasadas":    len(da),
            "canceladas":   len(dc),
            "fora_sla":     len(ds),
            "taxa_atraso":  round(len(da)/len(dm)*100, 1) if dm else 0,
            "tipos":        dict(Counter(r["tipo"] for r in dm if r["tipo"]).most_common(5)),
            "areas":        dict(Counter(r["area"] for r in dm if r["area"]).most_common(3)),
            "por_mes":      designer_por_mes,
            "demandas_atrasadas": [
                {"titulo": r["titulo"][:50], "prazo": r["prazo"], "status": r["status"], "area": r["area"]}
                for r in da[:10]
            ],
        }

    return {
        "gerado_em":         hoje,
        "meses":             meses,
        "por_mes":           por_mes,
        # Totais globais (todos os meses desde corte)
        "total":             total,
        "atrasados":         len(atrasados),
        "cancelados":        len(cancelados),
        "fora_sla":          len(fora_sla),
        "finalizados":       len(finalizados),
        "em_aprovacao":      len(em_aprovacao),
        "taxa_atraso_geral": round(len(atrasados)/total*100, 1) if total else 0,
        "status_counts":     dict(Counter(r["status"] for r in rows).most_common()),
        "tipo_counts":       dict(Counter(r["tipo"] for r in rows if r["tipo"]).most_common(8)),
        "area_counts":       dict(Counter(r["area"] for r in rows if r["area"]).most_common(8)),
        "area_atrasados":    dict(Counter(r["area"] for r in atrasados if r["area"]).most_common(8)),
        "designers":         designers_data,
    }


def inject_and_save(summary, team, index_path, data_path_tpl):
    data_path = data_path_tpl.format(team=team)
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


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists("index.html"):
        base = "."
    else:
        base = script_dir

    index_path    = os.path.join(base, "index.html")
    data_path_tpl = os.path.join(base, "data_{team}.json")

    print(f"\nBuscando dados do Notion (DB: {NOTION_DB_ID})...")
    all_pages = fetch_all(NOTION_DB_ID)
    print(f"  {len(all_pages)} páginas totais")

    for team in ["creat", "red"]:
        projeto_val = TEAM_PROJETO[team]
        rows = []
        for p in all_pages:
            r = parse(p)
            if r["criado"] < "2026-01-01":
                continue
            if r["projeto"] != projeto_val:
                continue
            rows.append(r)

        print(f"\n[{team.upper()}] {len(rows)} demandas (Projeto JIRA='{projeto_val}')")
        names_found = Counter(r["designer"] for r in rows if r["designer"])
        print(f"  Designers: {dict(names_found.most_common(10))}")

        summary = build_summary(rows, team)
        inject_and_save(summary, team, index_path, data_path_tpl)


if __name__ == "__main__":
    main()
