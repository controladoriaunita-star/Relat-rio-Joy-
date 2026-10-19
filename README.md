# Relatório de Aporte · Joy+ Evans

Ferramenta web de análise de custos e projeção de aportes. Substitui as abas **Resumo** e
**Painel** do `Controle - Joy+ Evans.xlsm`, reproduzindo as fórmulas da planilha, e traz a aba
**Projeção**, onde cada setor lança as suas projeções mensais.

**Arquitetura:** front estático (`public/`) e API FastAPI (`api/index.py`) na **Vercel**;
banco Postgres e login no **Supabase**; dados de origem lidos do SharePoint pelo **Microsoft Graph**.

---

## 1. Deploy (Supabase + Vercel)

1. **Supabase:** crie o projeto e rode `supabase/migrations/20261019120000_inicial.sql`
   (SQL Editor ou `supabase db push`). Todas as tabelas ficam com RLS ativo e sem policies:
   o acesso é só pelo backend.
2. **Supabase › Authentication › URL Configuration:** em *Site URL* coloque a URL da Vercel
   (os links de convite e de recuperação de senha voltam para ela).
3. **Variáveis de ambiente** (Vercel › Settings › Environment Variables), modelo em `.env.example`:
   `DATABASE_URL` (pooler em modo transação, porta 6543), `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `SUPABASE_SERVICE_ROLE_KEY` e as `GRAPH_*`. `SUPABASE_JWT_SECRET` só em projetos com HS256.
4. **Vercel:** importe o repositório (raiz do repositório = esta pasta) com o preset *Other*.
   `vercel.json` já define a função Python e as rotas `/api/*`.
5. **Carga inicial** (na sua máquina, com `DATABASE_URL` e as chaves do Supabase no `.env`):
   ```bash
   python -m pip install -r requirements-dev.txt
   python -m backend.app.migrar planilha
   python -m backend.app.migrar admin seu.email@unitaengenharia.com.br "Seu Nome"
   ```
   O administrador recebe um convite por e-mail para definir a senha. Os demais usuários
   são cadastrados na aba API's › Usuários.

## 2. Uso local

```bash
python -m pip install -r requirements-dev.txt
python -m uvicorn backend.app.main:criar_app --factory --port 8060
```
Ou `INICIAR_SISTEMA.bat`. Sem `DATABASE_URL`, o banco é SQLite em `data/`. Com
`APORTE_AUTH_LOCAL=1` no `.env`, o login vira um seletor de perfil, sem Supabase. Esse modo
só funciona com SQLite e nunca na Vercel.

---

## 3. Abas e perfis

| Aba | Conteúdo | Quem acessa |
|---|---|---|
| Resumo | Dashboard: KPIs, formação do aporte do mês (cascata da fórmula Z9), aporte do próximo mês, consumo da viabilidade, custo do mês por rubrica, conta da SPE, aportes programados e a tabela completa | todos |
| Painel | Realizado × Projetado × EVE (colunas A–F), verificação da planilha e linha do tempo jan/2024–dez/2030 | todos |
| Projeção | Grade mensal por setor/linha; o total por rubrica alimenta o "Projetado" do Resumo e do Painel | todos veem; cada setor edita as suas linhas |
| API's | Validador das 6 fontes, pendências de classificação, saldos bancários, viabilidade, usuários e histórico | diretor, adm |

**Perfis:** `adm` (desenvolvedores), `diretor` (Diretoria) e um perfil por setor com o código do
setor (`mkt`, `proj`, `inc`). Um setor novo (aba Projeção › Setores e linhas) cria o perfil
correspondente. Setores só editam meses a partir do mês corrente; diretor e adm editam qualquer mês.

**Login:** Supabase Auth (e-mail e senha). O navegador envia o access token (JWT) para a API,
que valida assinatura, audiência e emissor e busca o perfil na tabela `perfis`. Um usuário
desativado perde o acesso na hora e fica bloqueado no Supabase.

A **data-base** no topo substitui o `HOJE()` da planilha.

---

## 4. Fontes de dados

| Fonte | Aba no SharePoint (Graph) | Classificação |
|---|---|---|
| Custos SPE | `Custos SPE` | DePara por `Empresa - Obra - NProcesso` |
| Custos NN's | `Custos NN` | DePara por `Empresa - Obra - NProcesso - DocFiscal` |
| Controle Saídas | `Controle Saídas` | DePara por `Empresa_es - Num_es` |
| Controle Entradas | `Controle Entradas` | DePara por `Empresa_es - Num_es` |
| Transferências | `Transferências Bancarias` | — |
| Recebidas | `Recebidas` | — |

- Cada atualização grava uma carga por fonte. Se uma fonte falhar, o cálculo continua com a
  última carga válida e a aba API's mostra o erro.
- Lançamentos sem classificação ficam fora do cálculo e aparecem como pendência; a classificação
  feita na tela é gravada no DePara.
- O **saldo bancário** é lançado manualmente em API's › Saldos bancários (vale o último dia do mês, por conta).

---

## 5. Estrutura

```
sistema/
├── api/index.py            função serverless da Vercel (app FastAPI)
├── vercel.json · .vercelignore · requirements.txt (produção) · requirements-dev.txt
├── supabase/migrations/    esquema do Postgres
├── backend/app/
│   ├── config.py           .env, banco, Supabase, Graph e constantes das fórmulas
│   ├── excel_funcoes.py    EOMONTH, ROUND, texto e datas no padrão do Excel
│   ├── catalogo.py         rubricas, linhas do Resumo/Painel, viabilidade, setores iniciais
│   ├── motor/              cálculo puro: base.py, resumo.py, painel.py
│   ├── fontes/             definicoes, normalizacao (DePara), graph, excel, montagem
│   ├── db.py               Postgres (Supabase) ou SQLite, com o mesmo SQL
│   ├── auth.py             JWT do Supabase, Admin API, perfis e permissões
│   ├── servicos.py         casos de uso (fontes, cálculo, projeção, cadastros, migração)
│   ├── migrar.py           carga da planilha e criação do primeiro adm
│   └── main.py             API REST
├── backend/tests/          regressão contra o Excel, API, JWT e Graph real
└── public/                 interface (HTML, CSS com tokens Joy+, JS em módulos)
```

---

## 6. Testes

```bash
python -m pytest
set APORTE_TESTE_GRAPH=1 && python -m pytest backend/tests/test_graph_real.py
```

- **Regressão (`test_regressao_excel.py`)**: calcula Resumo e Painel a partir das tabelas do
  `.xlsm` e compara **célula a célula** com os valores salvos pelo Excel (todo o Resumo e
  ~5.000 células do Painel). Rode sempre que mexer no motor.
- **API (`test_api.py`)**: perfis, permissões por setor, bloqueio de mês passado, projeção
  refletindo no Resumo/Painel, custo do próximo mês automático, novo setor, usuário desativado,
  falha do Graph, pendência de classificação, saldos, premissas e histórico.
- **JWT (`test_auth.py`)**: assinatura, audiência, emissor e expiração do token do Supabase.
- **Graph real (`test_graph_real.py`)**: autenticação, permissões do token e colunas das 6 rotas.

Os testes usam SQLite; o mesmo SQL roda no Postgres do Supabase.

---

## 7. Diferenças e comportamentos da planilha

**Diferença intencional:** o custo do próximo mês (Resumo Z22) é digitado na planilha; no
sistema é **automático** (projeção dos setores + contas a pagar do próximo mês, coluna S). Assim o
aporte do próximo mês sai calculado. O teste de regressão usa o valor digitado para provar que o
restante bate com o Excel.

Comportamentos da planilha mantidos de propósito (cobertos pela regressão):

1. **Painel, coluna B (Projetado Mês)** filtra o tipo "Projetado (Mês)", que nenhuma linha usa: é sempre 0.
2. **Painel, coluna C (Projetado Total)** soma a projeção de **todos** os meses, inclusive os passados.
3. **Linha do tempo de custos/despesas**: em 2024 o sinal não é invertido. Em meses passados sem
   realizado, entra o projetado do mês.
4. **Resumo, Saídas**: "Pago Total até" usa `Data_es <` fim do mês corrente; "Pago no Mês" exige
   `Data_es` igual ao último dia do mês.
5. **Resumo Z17** (base 780.000) e **Painel H119** (ajuste 372.288,53) são premissas editáveis.
6. **"Total Mês (Incorrido + Projetado)"** é, pela fórmula, Pago no Mês + Contas a Pagar.
7. **Aportes programados**: 85% rotulado "Joy+" e 15% "Bapema", enquanto o bloco do aporte chama
   85% de "Investidor" e 15% de "Joy+".
8. **Painel L101** e **J122** dão `#VALUE!` na planilha e aparecem como `#VALOR!`.
