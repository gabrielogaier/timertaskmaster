# Estrutura do CSV

Cada usuário possui um arquivo mensal em:

```text
<pasta-base>\registros\<usuario>\AAAA-MM.csv
```

O delimitador utilizado é ponto e vírgula (`;`) e o arquivo é gravado em UTF-8 com BOM para facilitar a abertura no Excel.

| Coluna | Descrição |
|---|---|
| `registro_id` | UUID permanente do registro e chave de deduplicação |
| `usuario` | Nome configurado pelo usuário |
| `origem_registro` | `TIMER` ou `MANUAL` |
| `projeto` | Projeto selecionado no momento do registro |
| `tipo_atividade` | Tipo de atividade selecionado |
| `descricao` | Descrição informada pelo usuário |
| `inicio` | Data e hora inicial |
| `fim` | Data e hora final |
| `duracao_segundos` | Duração numérica em segundos |
| `duracao_formatada` | Duração em `HH:MM:SS` |
| `observacao` | Observação final opcional |
| `computador` | Nome do computador que criou o registro |
| `data_registro` | Data e hora em que o registro foi concluído |

Antes de acrescentar uma linha, o aplicativo verifica `registro_id`. Uma nova tentativa do mesmo registro não cria duplicação.

## CSV de auditoria

A exclusão de uma task não modifica o arquivo mensal original. O Timer Task Master cria um arquivo append-only em:

```text
<pasta-base>\registros\<usuario>\auditoria\AAAA-MM.csv
```

O mês corresponde ao mês do registro original. Assim, a leitura do histórico daquele período encontra tanto a task quanto sua auditoria.

| Coluna | Descrição |
|---|---|
| `acao_id` | UUID permanente da ação e chave de deduplicação |
| `registro_id` | UUID da task original |
| `acao` | Atualmente `EXCLUIR`; preparado para ações futuras |
| `data_hora_acao` | Data e hora da exclusão |
| `usuario_acao` | Usuário que executou a exclusão |
| `usuario_registro` | Usuário proprietário do registro original |
| `motivo` | Justificativa obrigatória |
| `computador` | Computador que criou a ação |
| `projeto` | Cópia do projeto original para auditoria |
| `tipo_atividade` | Cópia do tipo original |
| `descricao` | Cópia da descrição original |
| `inicio` | Início do registro original |
| `fim` | Fim do registro original |
| `duracao_segundos` | Duração original em segundos |
| `duracao_formatada` | Duração original em `HH:MM:SS` |
| `origem_registro` | `TIMER` ou `MANUAL` do registro original |
| `observacao` | Observação original |
| `data_registro` | Data em que a task original foi registrada |

A linha original permanece intacta. O estado atual é calculado ao cruzar `registro_id` com a ação de auditoria mais recente. Registros excluídos não entram nos totais, mas permanecem visíveis para conferência.
