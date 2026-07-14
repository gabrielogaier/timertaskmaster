# Timer Task Master

Timer Task Master reúne duas funções no mesmo aplicativo:

1. **Timer Task pessoal**: timer, registro manual, histórico, projetos, tipos de atividade, SQLite local e envio seguro para CSV.
2. **Gestão**: dashboard diário, cadastro de usuários monitorados e leitura de várias pastas de registros.

## Atualização do Timer Task

O instalador do Master utiliza o mesmo identificador de aplicativo do Timer Task. Ao executá-lo em um computador que já possui o Timer Task:

- o programa instalado é substituído pelo **Timer Task Master**;
- o executável e os atalhos antigos são removidos;
- os dados locais não são apagados;
- o banco continua em `%LOCALAPPDATA%\TimerTask\timertask.db`;
- projetos, tipos, configurações, timer ativo e tasks pendentes são preservados;
- a pasta-base dos CSVs continua configurada;
- antes da primeira abertura, é criado um backup em `%LOCALAPPDATA%\TimerTask\backups`;
- novas tabelas de gestão são acrescentadas ao mesmo SQLite.

Os CSVs já registrados também não são modificados pelo módulo de gestão. O dashboard realiza leitura e deduplicação por `registro_id`.

## Dashboard

Na aba **Usuários monitorados**, adicione uma pasta para cada usuário. O nome é detectado pela coluna `usuario` dos CSVs.

O dashboard mostra:

- horas registradas na data;
- quantidade de registros;
- registros manuais;
- usuários expansíveis;
- projetos e total por projeto;
- atividades com início, fim, tipo, origem e observação;
- registros excluídos destacados de forma discreta em vermelho;
- horas válidas calculadas sem contabilizar registros excluídos.

## Exportação gerencial

O Dashboard possui um único botão **Exportar**. A janela de salvamento permite escolher:

- **Excel completo (`.xlsx`)**: cria as abas Resumo, Usuários, Projetos, Registros e Auditoria, com dois gráficos objetivos de horas por usuário e por projeto.
- **CSV detalhado (`.csv`)**: gera uma lista única dos registros filtrados, adequada para Power BI, tratamento externo ou importação em outro sistema.

A exportação respeita a data e todos os filtros atuais do Dashboard. Registros excluídos não entram nas horas válidas e aparecem na aba Auditoria do Excel ou com status `EXCLUÍDO` no CSV.

No Excel, o Resumo também é dinâmico após a exportação:

- filtros aplicados na tabela **Registros** recalculam horas, registros, manuais e excluídos;
- filtros na tabela **Usuários** recalculam os indicadores pelo conjunto visível de usuários;
- filtros na tabela **Projetos** recalculam os indicadores e o gráfico pelo conjunto visível de projetos;
- a aba Resumo informa qual tabela está controlando os indicadores;
- quando mais de uma tabela estiver filtrada, a prioridade é Registros, Usuários e depois Projetos.
- todas as durações visíveis usam o padrão `HH:MM h`; no Excel, as células são durações reais com formato `[h]:mm`, permitindo somas acima de 24 horas sem horas decimais.

## Exclusão com auditoria

Na aba **Histórico**, o usuário pode excluir um registro informado incorretamente. A exclusão é lógica:

- a linha original do CSV mensal não é apagada nem alterada;
- o registro deixa de contabilizar horas no Histórico e no Dashboard;
- o motivo da exclusão é obrigatório;
- a ação é gravada em um CSV append-only de auditoria;
- cada ação possui `acao_id`, evitando duplicação em reenvios;
- em falha de rede, a exclusão permanece no SQLite e é reenviada por **Registrar Tasks**.

Estrutura:

```text
<pasta-base>\registros\<usuario>\AAAA-MM.csv
<pasta-base>\registros\<usuario>\auditoria\AAAA-MM.csv
```

O filtro **Ativos | Excluídos | Todos** permite consultar o histórico completo. No Master, registros excluídos aparecem em vermelho e continuam disponíveis ao expandir o usuário, mas não entram nos totais.

## Execução em desenvolvimento

- `run_timertaskmaster.bat`: execução normal.
- `run_debug.bat`: execução com terminal aberto.
- `finalizar_timertaskmaster.bat`: encerra processos desta pasta.

Os scripts verificam `PySide6` e `openpyxl` antes de iniciar. Quando uma dependência estiver ausente, ela é instalada automaticamente no ambiente virtual `.venv`. Na primeira execução ou após atualização do `requirements.txt`, é necessário acesso à internet para baixar os pacotes.

## Build

- `build_executavel.bat`: gera `dist\Timer Task Master.exe`.
- `build_installer.bat`: gera o executável e depois `dist\installer\TimerTaskMaster-Setup.exe`.

## Dados locais

```text
%LOCALAPPDATA%\TimerTask\
├── timertask.db
├── timertask.db-wal
├── timertask.db-shm
└── logs\
```

## Autoria

Desenvolvido por **gabrielogaier**.

## Exportação por período

O botão **Exportar** permite escolher entre:

- os filtros atuais do Dashboard, incluindo a data exibida;
- um ano e um ou vários meses, inclusive o ano inteiro.

Na exportação por período, o gestor também pode decidir se deseja aplicar os filtros atuais de projeto, tipo, origem e status.
