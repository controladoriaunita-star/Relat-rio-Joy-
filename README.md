# Relatório de Aporte · Joy+ Evans

Ferramenta web de análise de custos e projeção de aportes. Substitui as abas **Resumo** e
**Painel** do `Controle - Joy+ Evans.xlsm`, reproduzindo as fórmulas da planilha, e traz a aba
**Projeção**, onde cada setor lança as suas projeções mensais.

**Arquitetura:** front estático (`public/`) e API FastAPI (`api/index.py`) na **Vercel**;
banco Postgres e login no **Supabase**; dados de origem lidos do SharePoint pelo **Microsoft Graph**.

---

## 1. Deploy (Supabase + Vercel)

1. **Supabase:** crie o projeto e rode, em ordem, os arquivos de `supabase/migrations/`
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

**Testar os acessos de cada perfil** (sem Supabase, sem mexer no banco de produção):
```bash
python -m backend.app.dev
```
Abre em http://127.0.0.1:8061 com SQLite (`data/`), login ligado e um usuário de teste por
papel (admin, diretor e cada setor). O perfil é trocado no seletor do topo da tela. O Graph é o
do `.env`, então "Atualizar do SharePoint" funciona como em produção.

---

## 3. Abas e perfis

| Aba | Conteúdo | Quem acessa |
|---|---|---|
| Resumo | Layout da aba Resumo da planilha: tabela por rubrica e Relatório de Aporte (aporte do mês, conta da SPE, próximo mês e aportes programados) | admin, diretor |
| Dashboards | Gasto × projetado, recebimentos, custos por rubrica, setores que mais gastaram e acerto da projeção. A exposição de caixa (pontos A–D) está oculta: `MOSTRAR_EXPOSICAO` em `dashboards.js` | admin, diretor |
| Painel | Realizado × Projetado × EVE (colunas A–F), conciliação com o extrato e linha do tempo jan/2024–dez/2030 | admin, diretor |
| Projeção | Grade mensal por setor/linha; o total por rubrica alimenta o "Projetado" do Resumo e do Painel | todos; cada setor edita as suas linhas |
| API's | Validador das 7 fontes, pendências de classificação, saldos bancários, viabilidade, usuários, permissões e histórico | admin, diretor |

**Permissões (padrão Unità v1):** tabelas `profiles`, `roles`, `permissions`,
`role_permissions` e `user_roles` (migração `20261020150000_papeis_e_permissoes.sql`).

| Papel | Quem | Permissões iniciais |
|---|---|---|
| `admin` | Desenvolvedores | todas (toda permissão nova nasce concedida ao admin) |
| `diretor` | Diretoria | todas, menos `setores.gerenciar` e `usuarios.gerenciar` |
| `mkt`, `proj`, `inc`… | um papel por setor, com o código do setor | `projecao.ver` |

Permissões: `resumo.ver`, `dashboards.ver`, `painel.ver`, `projecao.ver`, `projecao.editar_todos_setores`,
`projecao.editar_meses_passados`, `apis.ver`, `fontes.atualizar`, `fontes.classificar`,
`saldos.editar`, `premissas.editar`, `setores.gerenciar` e `usuarios.gerenciar`. Quem tem
`projecao.ver` edita as linhas dos setores dos seus papéis, a partir do mês corrente.

Um setor novo (aba Projeção › Setores e linhas) cria o papel correspondente com `projecao.ver`.
As concessões são ajustadas em API's › Permissões (matriz papel × permissão), sem deploy; o
papel `admin` fica sempre com todas. O backend valida cada rota pela permissão; as funções
`auth_has_permission`, `auth_is_admin` e `auth_my_permissions` ficam no banco para uso futuro.

**Login (ativo):** a tela de login do Supabase é o padrão (`APORTE_LOGIN_ATIVO` ausente ou `1`).
Só com `APORTE_LOGIN_ATIVO=0` (Vercel ou `.env`) o sistema volta ao acesso direto, sem login, com o
perfil `APORTE_PERFIL_SEM_LOGIN` (padrão `admin`) e sem gestão de usuários: uso emergencial.

**Como funciona:** Supabase Auth (e-mail e senha). O navegador envia o access token (JWT) para a API,
que valida assinatura, audiência e emissor e busca o perfil e os papéis nas tabelas `profiles` e `user_roles`. Um usuário
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
| Saldos bancários | `Saldo` (tabela Consulta2) | — |

- Cada atualização grava uma carga por fonte. Se uma fonte falhar, o cálculo continua com a
  última carga válida e a aba API's mostra o erro.
- Lançamentos sem classificação ficam fora do cálculo e aparecem como pendência; a classificação
  feita na tela é gravada no DePara.
- O **saldo bancário** vem da aba `Saldo` do SharePoint: para cada conta vale o último lançamento do
  mês, e a soma das contas é o saldo do mês anterior no cálculo do aporte. API's › Saldos bancários
  mostra os lançamentos lidos e marca os de fim de mês.

---

**Leitura do SharePoint:** o `usedRange` traz o que estiver abaixo da tabela (linha de total,
notas). Linhas sem nenhum identificador (empresa, número, data...) são ignoradas e contadas em
`ignoradas` na aba API's. Antes da correção, o total de "Controle Entradas" (2.117.312,68) e
outro valor solto (1.130.800) entravam como Aporte Holding e inflavam o Saldo de Caixa do Painel.

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
│   ├── migrar.py           carga da planilha e criação do primeiro admin
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
- **Graph real (`test_graph_real.py`)**: autenticação, permissões do token e colunas das 7 rotas.

Os testes usam SQLite; o mesmo SQL roda no Postgres do Supabase.

---

## 7. Diferenças e comportamentos da planilha

**Regra do aporte:** aporte necessário = custos do mês (pago + a pagar + projetado) + caixa mínimo
(R$ 100 mil) − saldo bancário do fim do mês anterior − receitas do mês; nunca negativo.
**Receitas do mês** = tudo o que a aba **Recebidas** registra no mês selecionado (qualquer
cliente, qualquer dia do mês). Hoje a Recebidas traz os aportes do investidor; quando houver
vendas, elas entram pela mesma tabela. Por isso o aporte mostrado é o que ainda falta aportar.
Divisão: 85% investidor e 15% Joy+. Tudo segue o mês da data-base: qualquer data dentro do mês
entra naquele mês (fim de mês).

**Correções aprovadas em relação à planilha (out/2026):**

1. **Controle Saídas** entram pelo mês da data. A planilha só contava como "Pago no Mês" a
   saída do último dia do mês; as demais caíam em "Pago Total até" o mês anterior.
2. **Receita do mês** vem da aba Recebidas (out/2026). Antes eram as entradas do Controle
   Entradas que não são aporte (rendimentos de aplicação, que deixaram de entrar no aporte).
3. **Conta da SPE** é o fluxo do mês: saldo inicial + receitas + aporte − custos = saldo final
   (o caixa mínimo, quando há aporte), com os aportes já recebidos no mês e o que falta receber.
   A planilha usava o saldo de dois meses antes, todos os recebimentos desde o início e uma
   base fixa de 780.000 (Z13:Z18).
4. **Aporte do próximo mês** segue a mesma regra, a partir do saldo final projetado e da
   receita projetada. A planilha partia do saldo do item 3 e ignorava a receita (Z24).
5. **Custo do próximo mês** (Z22) é automático: projeção dos setores + contas a pagar do
   próximo mês (coluna S). Na planilha é digitado.
6. Rótulo corrigido: "Total Mês (Pago + A Pagar)" (a fórmula é J + L).
7. **Aportes programados** (Y32:Y43) viraram o **cronograma do aporte do mês**: o aporte
   necessário é dividido em 1 a 12 parcelas com data no mês. Cada parcela guarda o percentual
   do aporte; a última fica com o restante, então a soma é sempre o aporte do mês, mesmo que os
   custos mudem. O status (recebido, parcial, a receber) compara com os aportes já recebidos
   no mês. Sem cronograma, é parcela única no dia 1. Na planilha eram dois valores fixos de
   425.000 rotulados "85% Joy+ · 15% Bapema"; aqui a divisão é Investidor 85% · Joy+ 15%.
   Como as Recebidas já abatem o aporte, o status das parcelas usa só as transferências da
   holding no mês ("Aporte a receber" = aporte necessário − transferências da holding).

O teste de regressão compara todas as demais células com o Excel e calcula, a partir dos
dados, a diferença esperada do item 1. `test_regras_aporte.py` cobre as regras acima.

**Revisão do Painel (out/2026)** — detalhes em `backend/app/motor/painel.py` (P1–P11):

- **Corte único:** coluna A = realizado até o mês de análise (fim do mês anterior à data-base);
  B = projeção do mês corrente; C = projeção do mês corrente até dez/2030; D = A + C. Meses
  passados mostram só o realizado. A planilha somava a projeção de todos os meses em C (contando
  em dobro o que já foi realizado), deixava B sempre zero e deixava o mês corrente fora de A e C
  em receitas, resultado e sócios.
- **Totais:** Margem Operacional = Receita Líquida − custos (era só a soma dos custos); Resultado
  e Saldo de Caixa passam a ter o realizado (coluna A era zero fixo). F = % do EVE (receitas:
  D ÷ E; custos e despesas: % consumido, em vermelho acima de 100%).
- **Recebidas:** aportes do investidor na linha Aporte Investidor em todos os meses; Recebidas de
  outros clientes (vendas) em Clientes - Direto com SPE. Rendimentos pelo mês da data.
- **Caixa:** a linha do tempo do Saldo de Caixa (Banco) é o fluxo do mês (operação + sócios) e a
  linha "Saldo de caixa acumulado (banco)" acumula a partir do ajuste inicial (premissa). No mês
  de análise ela é igual à coluna A, e o cartão **Conciliação com o extrato** compara com a aba
  Saldo: diferença ≠ 0 indica lançamento sem classificação ou ajuste a revisar.
- **Limpeza:** sem `#VALOR!`, sem sinal invertido em 2024, coluna E vazia onde não há EVE
  (sócios, saldo do banco) e Resultado / VGV só no EVE. Botão "Ocultar linhas zeradas".

`test_regressao_excel.py` continua comparando com a planilha todas as células que não estão na
lista de correções (`COLUNAS_CORRIGIDAS`, `LINHAS_*_CORRIGIDAS`), e verifica com os dados da
planilha que a linha do tempo bate com as colunas e que o acumulado bate com o saldo.

Comportamentos da planilha mantidos (cobertos pela regressão):

1. **Painel H119** (ajuste 372.288,53) é premissa editável: saldo inicial e o que as fontes não trazem.
2. Realizado de custos e despesas (coluna A) e EVE de cada rubrica, iguais à planilha.
