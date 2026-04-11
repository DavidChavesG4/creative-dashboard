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

DATABASES = {
    "creat": "2e0b431349e180498fe0cbaf43c58f21",
    "red":   "2e0b431349e181a091fd000b23ac1a37",
}

CORTE = "2026-04-01"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

STATUS_ATRASAVEIS = {"Enviado", "Na fila", "Em produção", "Alteração"}

# Designers fixos por time — nomes exatamente como aparecem no Notion
DESIGNERS = {
    "creat": ["Flávia Lima", "Neemias Amaral", "Pedro Marcondes", "Vitor Santos Serodeo", "Matheus Gonçalves"],
    "red":   ["Flávia Lima", "Neemias Amaral", "Pedro Marcondes", "Vitor Santos Serodeo", "Matheus Gonçalves"],
}

# Variações de nome aceitas (Notion pode ter nome levemente diferente)
NAME_MAP = {
    "Vitor Serodeo":        "Vitor Santos Serodeo",
    "Vitor Santos Serodeo": "Vitor Santos Serodeo",
    "Neemias":              "Neemias Amaral",
    "Flavia Lima":          "Flávia Lima",
    "Matheus Goncalves":    "Matheus Gonçalves",
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
        # título pode estar em chave vazia ou "Nome" ou "Name"
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
        "prioridade": sel("Prioridade"),
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

    designers_data = {}
    for designer in DESIGNERS[team]:
        dm   = [r for r in rows if r["designer"] == designer]
        da   = [r for r in dm if r["atrasado"]]
        df   = [r for r in dm if r["status"] in ["Finalizado", "Aprovado"]]
        dc   = [r for r in dm if r["status"] == "Cancelada"]
        ds   = [r for r in dm if r["fora_sla"]]
        dand = [r for r in dm if r["status"] in ["Na fila", "Em produção", "Enviado", "Alteração", "Revisão"]]
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
            "demandas_atrasadas": [
                {"titulo": r["titulo"][:50], "prazo": r["prazo"], "status": r["status"], "area": r["area"]}
                for r in da[:10]
            ],
        }

    return {
        "gerado_em":         hoje,
        "corte":             CORTE,
        "total":             total,
        "atrasados":         len(atrasados),
        "cancelados":        len(cancelados),
        "fora_sla":          len(fora_sla),
        "finalizados":       len(finalizados),
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
    # Substitui o bloco correto no HTML: DATA_CREAT ou DATA_RED
    key = team.upper()
    html = re.sub(
        rf"const DATA_{key} = \{{.*?\}};",
        f"const DATA_{key} = {data_js};",
        html, flags=re.DOTALL
    )

    with open(index_path, "w") as f:
        f.write(html)
    print(f"  {index_path} — DATA_{key} atualizado")


def main():
    # Detecta raiz (GitHub Actions) vs local (pasta dashboard/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists("index.html"):
        base = "."
    else:
        base = script_dir

    index_path    = os.path.join(base, "index.html")
    data_path_tpl = os.path.join(base, "data_{team}.json")

    for team, db_id in DATABASES.items():
        print(f"\n[{team.upper()}] Buscando dados do Notion (DB: {db_id})...")
        pages = fetch_all(db_id)
        rows  = [r for p in pages for r in [parse(p)] if r["criado"] >= CORTE]
        print(f"  {len(rows)} demandas desde {CORTE}")

        # Debug: nomes encontrados no campo Creative
        names_found = Counter(r["designer"] for r in rows if r["designer"])
        print(f"  Designers encontrados: {dict(names_found.most_common(10))}")

        summary = build_summary(rows, team)
        inject_and_save(summary, team, index_path, data_path_tpl)


if __name__ == "__main__":
    main()
