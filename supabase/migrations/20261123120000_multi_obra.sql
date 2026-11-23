-- Relatório de Aporte · Joy+ — várias obras no mesmo app.
--
-- Cria o cadastro de obras e a coluna `obra` nas tabelas de dados de cada obra
-- (setores, depara, parametros, cargas, historico). Linhas e projeções seguem o setor.
-- Tudo o que já existe passa a ser da obra "evans". A Berrini entra cadastrada.
-- Rode ANTES de publicar a versão multi-obra do código (a versão atual continua
-- funcionando depois dela). Pode ser rodada mais de uma vez.

begin;

create table if not exists public.obras (
    codigo text primary key,
    nome   text not null,
    ordem  integer not null default 0,
    ativo  integer not null default 1,
    config text not null default '{}'
);
alter table public.obras enable row level security;

insert into public.obras (codigo, nome, ordem, config) values
  ('evans', 'Evans', 0, '{"empresa_spe": 73, "cliente_investidor": 8213, "historico_aporte_investidor": "APORTE Bapema Kalil Evans I Spe Ltda", "graph_item_id": "01UQIHIUUULNCLXTBFYFBJU2OHULC6J4JV", "arquivo_excel": "Controle - Joy+ Evans.xlsm"}'),
  ('berrini', 'Berrini', 1, '{"empresa_spe": 67, "graph_item_id": "01UQIHIUS2VNXRZMM4HRAIZUPOG3JFPH7A", "arquivo_excel": "Controle - Joy+ Berrini.xlsm", "abas": {"custos_nn": "Custos_NN''s", "transferencias": "Transferência Bancária", "recebidas": "Recebidos"}}')
on conflict (codigo) do nothing;

-- ---------- setores: código único por obra ----------
alter table public.setores add column if not exists obra text not null default 'evans' references public.obras (codigo);
alter table public.setores drop constraint if exists setores_codigo_key;
create unique index if not exists setores_obra_codigo_key on public.setores (obra, codigo);

-- ---------- depara: chave (obra, fonte, chave) ----------
alter table public.depara add column if not exists obra text not null default 'evans' references public.obras (codigo);
do $$ begin
  if exists (select 1 from information_schema.key_column_usage
             where table_schema = 'public' and table_name = 'depara' and constraint_name = 'depara_pkey'
             group by constraint_name having count(*) = 2) then
    alter table public.depara drop constraint depara_pkey;
    alter table public.depara add primary key (obra, fonte, chave);
  end if;
end $$;

-- ---------- parametros: chave (obra, chave) ----------
alter table public.parametros add column if not exists obra text not null default 'evans' references public.obras (codigo);
do $$ begin
  if exists (select 1 from information_schema.key_column_usage
             where table_schema = 'public' and table_name = 'parametros' and constraint_name = 'parametros_pkey'
             group by constraint_name having count(*) = 1) then
    alter table public.parametros drop constraint parametros_pkey;
    alter table public.parametros add primary key (obra, chave);
  end if;
end $$;

-- ---------- cargas e histórico ----------
alter table public.cargas add column if not exists obra text not null default 'evans' references public.obras (codigo);
create index if not exists ix_cargas_obra_fonte on public.cargas (obra, fonte, id);
alter table public.historico add column if not exists obra text;
update public.historico set obra = 'evans'
 where obra is null and acao not like 'usuario.%' and acao not like 'permissao.%';

-- O valor padrão 'evans' fica: a versão anterior do código, ainda publicada entre esta
-- migração e o novo deploy, continua gravando na Evans. O código novo sempre informa a obra.

commit;
