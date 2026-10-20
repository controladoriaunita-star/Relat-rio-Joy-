-- Relatório de Aporte · Joy+ Evans — permissões no padrão Unità v1
-- (papéis, permissões e concessões por usuário, mesmo modelo do App-QuadrodeConcorrencia).
--
-- Adaptações ao app:
--   * Papéis: admin (desenvolvedores), diretor (Diretoria) e um papel por setor, com a chave
--     igual ao código do setor (mkt, proj, inc...). O backend cria o papel de um setor novo.
--   * Permissões do app (resumo.ver, projecao.ver, fontes.atualizar...) no lugar de "membro".
--   * Substitui a tabela perfis: os usuários existentes viram profiles + user_roles
--     (o perfil "adm" vira o papel "admin"). Remove também as tabelas permissoes e visoes,
--     da matriz por perfil que este modelo substitui.
--   * O acesso aos dados continua só pelo backend; as funções auth_* ficam disponíveis
--     para o front-end (supabase.rpc) e para políticas RLS futuras.
--
-- Pode ser rodada mais de uma vez.

begin;

-- ---------- Tabelas ----------

create table if not exists public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  full_name   text not null default '',
  email       text,
  active      boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists public.roles (
  id          uuid primary key default gen_random_uuid(),
  key         text not null unique,
  name        text not null,
  description text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists public.permissions (
  id          uuid primary key default gen_random_uuid(),
  key         text not null unique,
  description text not null,
  created_at  timestamptz not null default now()
);

create table if not exists public.role_permissions (
  role_id       uuid not null references public.roles (id) on delete cascade,
  permission_id uuid not null references public.permissions (id) on delete cascade,
  created_at    timestamptz not null default now(),
  primary key (role_id, permission_id)
);

create table if not exists public.user_roles (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  role_id     uuid not null references public.roles (id) on delete cascade,
  granted_by  uuid references auth.users (id),
  created_at  timestamptz not null default now(),
  unique (user_id, role_id)
);

create index if not exists user_roles_user_id on public.user_roles (user_id);

-- ---------- Funções usadas pelo app e pelas políticas RLS ----------

create or replace function public.auth_has_permission(p_permission text)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1
      from public.user_roles ur
      join public.role_permissions rp on rp.role_id = ur.role_id
      join public.permissions p on p.id = rp.permission_id
      join public.profiles pr on pr.id = ur.user_id and pr.active
     where ur.user_id = auth.uid()
       and p.key = p_permission
  );
$$;

create or replace function public.auth_is_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1
      from public.user_roles ur
      join public.roles r on r.id = ur.role_id
      join public.profiles pr on pr.id = ur.user_id and pr.active
     where ur.user_id = auth.uid() and r.key = 'admin'
  );
$$;

-- O front-end pode chamar: supabase.rpc('auth_my_permissions')
create or replace function public.auth_my_permissions()
returns table (permission text) language sql stable security definer set search_path = public as $$
  select distinct p.key
    from public.user_roles ur
    join public.role_permissions rp on rp.role_id = ur.role_id
    join public.permissions p on p.id = rp.permission_id
    join public.profiles pr on pr.id = ur.user_id and pr.active
   where ur.user_id = auth.uid();
$$;

revoke execute on function public.auth_has_permission(text), public.auth_is_admin(), public.auth_my_permissions() from anon;

-- ---------- Gatilhos ----------

-- Cria o perfil de todo usuário novo do Auth (convites antigos do app gravavam "nome").
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, full_name, email)
  values (new.id,
          coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'nome', ''),
          new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Toda permissão nova já nasce concedida ao papel admin.
create or replace function public.grant_new_permission_to_admin()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.role_permissions (role_id, permission_id)
  select r.id, new.id from public.roles r where r.key = 'admin'
  on conflict do nothing;
  return new;
end;
$$;

drop trigger if exists permissions_grant_admin on public.permissions;
create trigger permissions_grant_admin
  after insert on public.permissions
  for each row execute function public.grant_new_permission_to_admin();

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();
drop trigger if exists roles_set_updated_at on public.roles;
create trigger roles_set_updated_at before update on public.roles
  for each row execute function public.set_updated_at();

-- ---------- RLS ----------

alter table public.profiles enable row level security;
alter table public.roles enable row level security;
alter table public.permissions enable row level security;
alter table public.role_permissions enable row level security;
alter table public.user_roles enable row level security;

drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles for select to authenticated
  using (id = auth.uid() or public.auth_is_admin());
drop policy if exists profiles_admin on public.profiles;
create policy profiles_admin on public.profiles for update to authenticated
  using (public.auth_is_admin()) with check (public.auth_is_admin());

drop policy if exists roles_select on public.roles;
create policy roles_select on public.roles for select to authenticated using (true);
drop policy if exists roles_admin on public.roles;
create policy roles_admin on public.roles for all to authenticated
  using (public.auth_is_admin()) with check (public.auth_is_admin());

drop policy if exists permissions_select on public.permissions;
create policy permissions_select on public.permissions for select to authenticated using (true);
drop policy if exists permissions_admin on public.permissions;
create policy permissions_admin on public.permissions for all to authenticated
  using (public.auth_is_admin()) with check (public.auth_is_admin());

drop policy if exists role_permissions_select on public.role_permissions;
create policy role_permissions_select on public.role_permissions for select to authenticated using (true);
drop policy if exists role_permissions_admin on public.role_permissions;
create policy role_permissions_admin on public.role_permissions for all to authenticated
  using (public.auth_is_admin()) with check (public.auth_is_admin());

drop policy if exists user_roles_select on public.user_roles;
create policy user_roles_select on public.user_roles for select to authenticated
  using (user_id = auth.uid() or public.auth_is_admin());
drop policy if exists user_roles_admin on public.user_roles;
create policy user_roles_admin on public.user_roles for all to authenticated
  using (public.auth_is_admin()) with check (public.auth_is_admin());

-- ---------- Dados iniciais ----------

-- Papéis antes das permissões: o gatilho concede cada permissão nova ao admin.
insert into public.roles (key, name, description) values
  ('admin', 'Administrador', 'Desenvolvedores: acesso total ao app'),
  ('diretor', 'Diretoria', 'Vê todas as abas e edita todos os setores e meses')
on conflict (key) do nothing;

-- Um papel por setor (mkt, proj, inc...).
insert into public.roles (key, name, description)
select s.codigo, s.nome, 'Setor ' || s.nome from public.setores s
on conflict (key) do nothing;

insert into public.permissions (key, description) values
  ('resumo.ver', 'Ver a aba Resumo'),
  ('dashboards.ver', 'Ver a aba Dashboards'),
  ('painel.ver', 'Ver a aba Painel'),
  ('projecao.ver', 'Ver a aba Projeção e editar as linhas do próprio setor'),
  ('projecao.editar_todos_setores', 'Editar a projeção de qualquer setor'),
  ('projecao.editar_meses_passados', 'Editar meses anteriores ao corrente'),
  ('apis.ver', 'Ver a aba API''s (fontes, pendências, saldos, viabilidade e histórico)'),
  ('fontes.atualizar', 'Atualizar as fontes (SharePoint ou Excel)'),
  ('fontes.classificar', 'Classificar lançamentos pendentes (DePara)'),
  ('saldos.editar', 'Lançar e excluir saldos bancários'),
  ('premissas.editar', 'Editar premissas do aporte e viabilidade'),
  ('setores.gerenciar', 'Criar e alterar setores e linhas de projeção'),
  ('usuarios.gerenciar', 'Gerenciar usuários, papéis e permissões dentro do app')
on conflict (key) do nothing;

-- Admin: todas (também cobre permissões criadas antes do papel admin existir).
insert into public.role_permissions (role_id, permission_id)
select r.id, p.id from public.roles r cross join public.permissions p where r.key = 'admin'
on conflict do nothing;

-- Diretoria: tudo, menos gerenciar setores e usuários.
insert into public.role_permissions (role_id, permission_id)
select r.id, p.id from public.roles r cross join public.permissions p
 where r.key = 'diretor' and p.key not in ('setores.gerenciar', 'usuarios.gerenciar')
on conflict do nothing;

-- Setores: só a aba Projeção (editam as linhas do próprio setor).
insert into public.role_permissions (role_id, permission_id)
select r.id, p.id from public.roles r join public.setores s on s.codigo = r.key
  cross join public.permissions p
 where p.key = 'projecao.ver'
on conflict do nothing;

-- Perfis para usuários que já existiam antes desta migration.
insert into public.profiles (id, full_name, email)
select id, coalesce(raw_user_meta_data ->> 'full_name', raw_user_meta_data ->> 'nome', ''), email from auth.users
on conflict (id) do nothing;

-- ---------- Migração da tabela perfis (modelo anterior) ----------

do $$
begin
  if to_regclass('public.perfis') is not null then
    update public.profiles pr
       set full_name = pe.nome, email = pe.email, active = pe.ativo = 1
      from public.perfis pe
     where pe.usuario_id = pr.id;

    insert into public.user_roles (user_id, role_id)
    select pe.usuario_id, r.id
      from public.perfis pe
      join public.roles r on r.key = case pe.perfil when 'adm' then 'admin' else pe.perfil end
    on conflict (user_id, role_id) do nothing;

    drop table public.perfis;
  end if;
end;
$$;

drop table if exists public.permissoes;
drop table if exists public.visoes;

commit;
