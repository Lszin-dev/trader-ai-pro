-- Executar como uma única instrução no SQL Editor do Supabase.
do $migration$
begin
-- TRADER AI PRO: pesquisa prospectiva de candidatos, sem ordens reais.
-- Tabela independente; não modifica historico_sinais.
create table if not exists public.pesquisa_sinais (
    provider text not null,
    ativo text not null,
    strategy_version text not null,
    candle_time timestamptz not null,
    observed_at timestamptz not null,
    registered_at timestamptz not null default clock_timestamp(),
    direction text not null check (direction in ('CALL','PUT')),
    expiration_minutes integer not null check (expiration_minutes in (1,5)),
    entry_at timestamptz not null,
    target_at timestamptz not null,
    score double precision not null check (score between 0 and 100),
    features jsonb not null default '{}'::jsonb,
    status text not null default 'PENDENTE' check (status in ('PENDENTE','ACERTO','ERRO','EMPATE','SEM_DADOS')),
    entry_price double precision,
    final_price double precision,
    evaluated_at timestamptz,
    primary key (provider, ativo, strategy_version, candle_time, expiration_minutes),
    check (entry_at > observed_at),
    check (entry_at > registered_at),
    check (target_at = entry_at + expiration_minutes * interval '1 minute'),
    check (entry_at = date_trunc('minute', entry_at)),
    check (
      (status = 'PENDENTE' and entry_price is null and final_price is null and evaluated_at is null)
      or (status = 'SEM_DADOS' and entry_price is null and final_price is null and evaluated_at is not null)
      or (status in ('ACERTO','ERRO','EMPATE') and entry_price > 0 and final_price > 0 and evaluated_at is not null)
    )
);
create index if not exists pesquisa_sinais_pending_idx
    on public.pesquisa_sinais(provider, ativo, target_at)
    where status = 'PENDENTE';
alter table public.pesquisa_sinais enable row level security;
revoke all on table public.pesquisa_sinais from public, anon, authenticated;
grant select, insert, update on table public.pesquisa_sinais to service_role;
-- Dataset privado: acesso somente via servidor com credencial de serviço.

end;
$migration$;
