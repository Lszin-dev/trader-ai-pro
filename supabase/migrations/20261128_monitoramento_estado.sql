-- TRADER AI PRO: estado compartilhado do worker.
-- Execute no SQL Editor do Supabase. Não altera historico_sinais.
create table if not exists public.monitoramento_estado (
    provider text not null,
    ativo text not null,
    status text not null default 'error'
        check (status in ('observed', 'error', 'running')),
    sinal_candidato text not null default 'AGUARDAR'
        check (sinal_candidato in ('CALL', 'PUT', 'AGUARDAR')),
    motivo text not null default '',
    ultimo_ciclo timestamptz,
    ultimo_dado timestamptz,
    atualizado_em timestamptz not null default now(),
    detalhes jsonb not null default '{}'::jsonb,
    primary key (provider, ativo)
);

alter table public.monitoramento_estado enable row level security;

revoke all on table public.monitoramento_estado from anon, authenticated;
grant select on table public.monitoramento_estado to anon, authenticated;
grant select, insert, update, delete on table public.monitoramento_estado to service_role;

drop policy if exists "monitoramento_estado_read" on public.monitoramento_estado;
create policy "monitoramento_estado_read"
    on public.monitoramento_estado
    for select
    to anon, authenticated
    using (true);

-- service_role bypasses RLS. The app can read with anon/authenticated,
-- while only the trusted worker/service role can write.
