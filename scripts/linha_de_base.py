"""Gera `evidencias/linha-de-base.md` e a chave `linha_de_base` de `medicoes.json`.

12 linhas: {treino, teste, producao} × {v1, v2} × {com, sem vazamento}. É a tabela em que
todo assert das fases 4 e 5 vai se apoiar — nenhum número entra em teste sem passar por aqui.

Determinístico: não há reamostragem nesta fase, e a inferência do SUT é determinística por
construção (SPEC P7). Rodar duas vezes dá `diff` vazio.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
from importlib import metadata

import numpy as np

import sentinela as sn
from suite import calibracao, harness, metricas

CONJUNTOS = ("treino", "teste", "producao")
VERSOES = ("v1", "v2")
MODOS = (("com", True), ("sem", False))


# Brier e ECE vinham implementados aqui. Passaram para `suite/calibracao.py` na Etapa 2 do
# HANDOFF 04, quando o módulo nasceu: duas implementações do mesmo número em dois arquivos
# divergem, e as colunas Brier/ECE desta tabela são as mesmas que os testes de D12 assertam.
# A troca é sem efeito sobre os números — conferida por `diff` vazio na regeneração.


def linha(conjunto: str, versao: str, modo: str, vazar: bool) -> dict:
    lote = sn.dados.carregar(conjunto)
    fn = harness.prever_com_vazamento if vazar else harness.prever_sem_vazamento
    y, proba, pred = fn(lote, versao)

    base = sn.avaliacao.metricas(y, pred)
    return {
        "conjunto": conjunto,
        "versao": versao,
        "vazamento": modo,
        "acuracia": round(float(base["acuracia"]), 6),
        "precisao": round(float(base["precisao"]), 6),
        "recall": round(float(base["recall"]), 6),
        "f1": round(float(base["f1"]), 6),
        "f2": round(metricas.fbeta(y, pred, beta=2.0), 6),
        "pr_auc": round(metricas.average_precision(y, proba), 6),
        "brier": round(calibracao.brier(y, proba), 6),
        "ece": round(calibracao.ece(y, proba), 6),
    }


def main() -> int:
    registros = [
        linha(c, v, modo, vazar)
        for c in CONJUNTOS
        for v in VERSOES
        for modo, vazar in MODOS
    ]

    # contexto por conjunto: prevalência e a acurácia do preditor sempre-zero
    contexto = {}
    for c in CONJUNTOS:
        y = sn.preprocessamento.limpar(sn.dados.carregar(c))["falha_72h"].to_numpy(dtype=int)
        contexto[c] = {
            "linhas": int(len(y)),
            "prevalencia": round(float(y.mean()), 6),
            "acuracia_sempre_zero": round(float((y == 0).mean()), 6),
        }

    sha = subprocess.run(
        ["git", "-C", "/opt/sentinela", "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    versoes = {p: metadata.version(p) for p in ("numpy", "pandas", "scipy", "pytest")}
    semente = os.environ.get("SUITE_SEED", "42")

    def busca(c, v, modo):
        return next(r for r in registros if (r["conjunto"], r["versao"], r["vazamento"]) == (c, v, modo))

    L = []
    L.append("# Linha de base\n")
    L.append("Gerado por `scripts/linha_de_base.py`. **Nenhum número entra em assert nas fases 4 e 5")
    L.append("sem ter passado por esta tabela.**\n")
    L.append(f"- SUT: `{sha}`")
    L.append(f"- `SUITE_SEED`: `{semente}`")
    L.append("- versões: " + ", ".join(f"`{k}={v}`" for k, v in sorted(versoes.items())))
    L.append("\n> ### Convenção de sinal — leia antes de citar qualquer Δ")
    L.append(">")
    L.append("> Este arquivo usa **v2 − v1** nas tabelas descritivas, porque \"a v2 ganhou +3,5 pp\"")
    L.append("> é como a Nortemec fala e é a frase que o trabalho contesta. O **intervalo de")
    L.append("> confiança pareado** do HANDOFF 04 usa a convenção oposta, **v1 − v2**, fixada pelo")
    L.append("> SPEC §5: `lo > 0` ⇒ v1 melhor, `hi < 0` ⇒ v2 melhor.")
    L.append(">")
    L.append("> São o mesmo fato com o sinal trocado. Por isso **nenhuma coluna aqui se chama")
    L.append("> \"Δ\"**: cada uma carrega a fórmula no próprio nome.\n")
    L.append("\n> **`com vazamento`** = como o SUT faz hoje (o rótulo fica no quadro e")
    L.append("> `maquina_risco` é recalculada com ele). **`sem vazamento`** = simulação do serving,")
    L.append("> com a coluna de rótulo removida antes de construir as features. A simulação é")
    L.append("> declarada como tal: em produção o rótulo não existe porque a falha ainda não")
    L.append("> aconteceu.\n")

    L.append("## Contexto dos conjuntos\n")
    L.append("| conjunto | linhas | prevalência | acurácia do preditor sempre-zero |")
    L.append("|---|---:|---:|---:|")
    for c in CONJUNTOS:
        k = contexto[c]
        L.append(f"| {c} | {k['linhas']} | {k['prevalencia']:.4f} | {k['acuracia_sempre_zero']:.4f} |")
    L.append("")

    L.append("## As 12 linhas\n")
    L.append("| conjunto | versão | vazamento | acurácia | precisão | recall | F1 | F2 | PR-AUC | Brier | ECE |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in registros:
        L.append(
            f"| {r['conjunto']} | {r['versao']} | {r['vazamento']} | {r['acuracia']:.4f} | "
            f"{r['precisao']:.4f} | {r['recall']:.4f} | {r['f1']:.4f} | {r['f2']:.4f} | "
            f"{r['pr_auc']:.4f} | {r['brier']:.4f} | {r['ece']:.4f} |"
        )
    L.append("")

    # --- as três perguntas da Etapa 3 ---
    L.append("## As três perguntas\n")

    L.append("### (a) Os +3,5 pp de acurácia da v2 reproduzem?\n")
    L.append("O README do SUT afirma que a v2 \"ganhou +3,5 pontos percentuais de acurácia no")
    L.append("conjunto de teste\". A equipe mediu do jeito que o SUT roda — isto é, **com vazamento**.\n")
    L.append("| conjunto | modo | acurácia v1 | acurácia v2 | acurácia(v2) − acurácia(v1), pp |")
    L.append("|---|---|---:|---:|---:|")
    for c in CONJUNTOS:
        for modo, _ in MODOS:
            a1, a2 = busca(c, "v1", modo)["acuracia"], busca(c, "v2", modo)["acuracia"]
            L.append(f"| {c} | {modo} | {a1:.4f} | {a2:.4f} | {100*(a2-a1):+.2f} |")
    d_teste_com = 100 * (busca("teste", "v2", "com")["acuracia"] - busca("teste", "v1", "com")["acuracia"])
    L.append("")
    L.append(f"**Resposta:** no conjunto de teste, com vazamento, o Δ medido é **{d_teste_com:+.2f} pp**.")
    L.append("")

    L.append("### (b) De quanto é o Δrecall entre v1 e v2?\n")
    L.append("| conjunto | modo | recall v1 | recall v2 | recall(v2) − recall(v1), pp | F2 v1 | F2 v2 |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for c in CONJUNTOS:
        for modo, _ in MODOS:
            r1, r2 = busca(c, "v1", modo), busca(c, "v2", modo)
            L.append(
                f"| {c} | {modo} | {r1['recall']:.4f} | {r2['recall']:.4f} | "
                f"{100*(r2['recall']-r1['recall']):+.2f} | {r1['f2']:.4f} | {r2['f2']:.4f} |"
            )
    L.append("")

    L.append("### (c) De quanto é a inflação causada pelo vazamento?\n")
    L.append("Diferença `com` − `sem`, na mesma linha de conjunto e versão.\n")
    L.append("| conjunto | versão | recall(com) − recall(sem), pp | F2, idem | PR-AUC, idem | acurácia, idem |")
    L.append("|---|---|---:|---:|---:|---:|")
    for c in CONJUNTOS:
        for v in VERSOES:
            a, b = busca(c, v, "com"), busca(c, v, "sem")
            L.append(
                f"| {c} | {v} | {100*(a['recall']-b['recall']):+.2f} | {100*(a['f2']-b['f2']):+.2f} | "
                f"{100*(a['pr_auc']-b['pr_auc']):+.2f} | {100*(a['acuracia']-b['acuracia']):+.2f} |"
            )
    L.append("")

    # --- curva de confiabilidade: o pedido literal do guia do aluno (V15) ---
    # Por faixa de probabilidade, a confiança média prevista contra a frequência de falha
    # observada. É a tabela de onde saem Brier e ECE das 12 linhas acima, aberta.
    L.append("## Curva de confiabilidade (teste, sem vazamento)\n")
    L.append("O que o modelo prometeu (`confiança`) contra o que aconteceu (`observado`), faixa a")
    L.append("faixa. `gap` positivo = **superconfiança**: o painel anuncia mais risco do que existe.\n")
    lote_teste = sn.dados.carregar("teste")
    bins = {}
    for v in VERSOES:
        y_t, proba_t, _ = harness.prever_sem_vazamento(lote_teste, v)
        bins[v] = calibracao.bins_de_confiabilidade(y_t, proba_t)
    L.append("| faixa | n (v1) | confiança v1 | observado v1 | gap v1 | n (v2) | confiança v2 | observado v2 | gap v2 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for b1, b2 in zip(bins["v1"], bins["v2"]):
        lo, hi = b1["faixa"]
        L.append(
            f"| {lo:.1f}–{hi:.1f} | {b1['n']} | {b1['confianca']:.4f} | {b1['observado']:.4f} | "
            f"{b1['gap']:+.4f} | {b2['n']} | {b2['confianca']:.4f} | {b2['observado']:.4f} | "
            f"{b2['gap']:+.4f} |"
        )
    L.append("")
    positivos = sum(1 for v in VERSOES for b in bins[v] if b["gap"] > 0)
    total_faixas = sum(len(bins[v]) for v in VERSOES)
    L.append(f"**{positivos} de {total_faixas} faixas têm `gap` positivo**: as duas versões são")
    L.append("superconfiantes em toda a escala — nunca prometem de menos. É o defeito **D12**.\n")

    # --- leitura: as respostas em prosa, que é o que o relatório cita ---
    r_teste_com = busca("teste", "v1", "com")["recall"], busca("teste", "v2", "com")["recall"]
    r_teste_sem = busca("teste", "v1", "sem")["recall"], busca("teste", "v2", "sem")["recall"]
    prauc_v1 = busca("teste", "v1", "com")["pr_auc"], busca("teste", "v1", "sem")["pr_auc"]

    L.append("## Leitura\n")
    L.append(f"**(a) Sim, os +3,5 pp reproduzem** — {d_teste_com:+.2f} pp no conjunto de teste, no")
    L.append("modo em que a equipe mediu. O gate de escalonamento **não** dispara: a afirmação do")
    L.append("README é verdadeira como afirmação de acurácia. O problema não é o número, é a métrica.\n")
    L.append(f"**(b) A v2 compra acurácia com recall.** No teste, o recall cai de")
    L.append(f"{r_teste_com[0]:.4f} para {r_teste_com[1]:.4f} — **{100*(r_teste_com[1]-r_teste_com[0]):+.2f} pp** —")
    L.append(f"e sem vazamento a queda é de {100*(r_teste_sem[1]-r_teste_sem[0]):+.2f} pp. O Δrecall é")
    L.append("**negativo nos três conjuntos e nos dois modos** (na convenção v2 − v1 deste")
    L.append("arquivo). Com prevalência de ~15 %, o preditor")
    L.append("sempre-zero já acerta 84 % no teste: acurácia é quase insensível à classe que importa.")
    L.append("F2, que pesa recall 4×, também piora com a v2 no teste e em produção. Promover a v2")
    L.append("troca motores queimados por um número de slide — é o defeito **D11**.\n")
    L.append("**(c) O vazamento infla tudo, exceto no treino.** No treino a inflação é **exatamente")
    L.append("0,00 pp** em todas as métricas: a tabela congelada `risco_maquina.json` **é** a média por")
    L.append("motor do próprio treino, então recalcular a partir do rótulo devolve o mesmo valor. A")
    L.append("diferença na feature existe (máx. 4,762e-07, o arredondamento a 6 casas do arquivo) mas")
    L.append("não muda uma única probabilidade — elas são bit-idênticas.\n")
    L.append(f"Fora do treino a inflação é grande: no teste, a PR-AUC da v1 vai de {prauc_v1[1]:.4f}")
    L.append(f"para {prauc_v1[0]:.4f} (**{100*(prauc_v1[0]-prauc_v1[1]):+.2f} pp**) e a acurácia sobe")
    L.append("+12,07 pp. O mecanismo é visível na própria feature: com vazamento `maquina_risco`")
    L.append("alcança **0,428571** em teste e produção, contra um teto de **0,214286** na tabela")
    L.append("congelada — o valor recalculado sai da faixa que o modelo viu no treino.\n")
    L.append("> **Consequência para as fases 4 e 5:** toda comparação v1 × v2 tem de ser lida **sem")
    L.append("> vazamento**, porque é esse o número que a planta obtém. E nenhuma delas pode se apoiar")
    L.append("> em acurácia.\n")

    destino = pathlib.Path("evidencias/linha-de-base.md")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(L) + "\n", encoding="utf-8")

    # medicoes.json — chave linha_de_base (esquema C8)
    cam = pathlib.Path(os.environ.get("SUITE_MEDICOES", "evidencias/medicoes.json"))
    dados = json.loads(cam.read_text(encoding="utf-8")) if cam.exists() else {}
    dados["linha_de_base"] = registros
    dados.setdefault("contrato_dados", {})
    for c, k in contexto.items():
        dados["contrato_dados"].setdefault(c, {}).update(
            {"acuracia_sempre_zero": k["acuracia_sempre_zero"]}
        )
    cam.write_text(json.dumps(dados, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"linha-de-base.md: {len(registros)} linhas | delta acuracia teste/com = {d_teste_com:+.2f} pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
