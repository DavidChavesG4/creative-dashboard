#!/usr/bin/env python3
"""
Gera o dashboard/data.json com dados do banco 2026 do Notion.
Roda pelo GitHub Actions e localmente para atualizar o dashboard.
"""

import os
import json
import requests
from datetime import date
from collections import Counter

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DB_ID = "2e0b431349e180498fe0cbaf43c58f21"
CORTE        = "2026-03-01"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

STATUS_ATRASAVEIS = {"Enviado", "Na fila", "Em produção", "Alteração"}


def fetch_all():
    results, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
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
        return arr[0].get("name", "") if arr else ""

    def chk(k):
        return props.get(k, {}).get("checkbox", False)

    def ttl():
        arr = props.get("", {}).get("title", [])
        return arr[0].get("plain_text", "") if arr else ""

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


def build_summary(rows):
    hoje = date.today().isoformat()
    total       = len(rows)
    atrasados   = [r for r in rows if r["atrasado"]]
    cancelados  = [r for r in rows if r["status"] == "Cancelada"]
    fora_sla    = [r for r in rows if r["fora_sla"]]
    finalizados = [r for r in rows if r["status"] in ["Finalizado", "Aprovado"]]

    designers_data = {}
    for designer in sorted(set(r["designer"] for r in rows if r["designer"] and r["designer"] != "David Chaves")):
        dm  = [r for r in rows if r["designer"] == designer]
        da  = [r for r in dm if r["atrasado"]]
        df  = [r for r in dm if r["status"] in ["Finalizado", "Aprovado"]]
        dc  = [r for r in dm if r["status"] == "Cancelada"]
        ds  = [r for r in dm if r["fora_sla"]]
        dand= [r for r in dm if r["status"] in ["Na fila", "Em produção", "Enviado", "Alteração", "Revisão"]]
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
        "gerado_em":        hoje,
        "total":            total,
        "atrasados":        len(atrasados),
        "cancelados":       len(cancelados),
        "fora_sla":         len(fora_sla),
        "finalizados":      len(finalizados),
        "taxa_atraso_geral":round(len(atrasados)/total*100, 1) if total else 0,
        "status_counts":    dict(Counter(r["status"] for r in rows).most_common()),
        "tipo_counts":      dict(Counter(r["tipo"] for r in rows if r["tipo"]).most_common(8)),
        "area_counts":      dict(Counter(r["area"] for r in rows if r["area"]).most_common(8)),
        "area_atrasados":   dict(Counter(r["area"] for r in atrasados if r["area"]).most_common(8)),
        "designers":        designers_data,
    }


def main():
    print("Buscando dados do Notion...")
    pages = fetch_all()
    rows  = [parse(p) for p in pages if parse(p)["criado"] >= CORTE]
    print(f"  {len(rows)} demandas (desde {CORTE})")

    summary = build_summary(rows)

    # No repo o index.html e data.json ficam na raiz (GitHub Pages serve de /)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root  = os.path.dirname(script_dir)  # dashboard/ está dentro do repo local, mas no Actions o script roda da raiz

    # Detecta se está rodando no GitHub Actions (raiz do repo) ou local (pasta dashboard/)
    index_path = "index.html" if os.path.exists("index.html") else os.path.join(script_dir, "index.html")
    data_path  = "data.json"  if os.path.exists("index.html") else os.path.join(script_dir, "data.json")

    with open(data_path, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  Salvo em {data_path}")

    # Injeta no index.html
    with open(index_path) as f:
        html = f.read()

    import re
    data_js = json.dumps(summary, ensure_ascii=False)
    html = re.sub(r"const DATA = \{.*?\};", f"const DATA = {data_js};", html, flags=re.DOTALL)

    with open(index_path, "w") as f:
        f.write(html)
    print(f"  {index_path} atualizado")


if __name__ == "__main__":
    main()
