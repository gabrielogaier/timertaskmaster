# Segurança

## Dados processados

O Timer Task Master armazena localmente configurações, projetos, tipos de atividade, timer ativo e registros pendentes em SQLite. Registros concluídos são enviados para a pasta CSV definida pelo usuário.

O aplicativo não possui serviço em nuvem, telemetria ou envio automático de dados para terceiros.

## Relato de vulnerabilidades

Não publique em uma issue dados pessoais, caminhos internos de rede, arquivos CSV reais ou bancos SQLite. Relate apenas a descrição técnica e passos reproduzíveis com dados fictícios.

## Recomendações de uso

- Use uma pasta compartilhada com permissões restritas aos usuários autorizados.
- Não publique o conteúdo de `%LOCALAPPDATA%\TimerTask`.
- Faça backup periódico da pasta de registros.
- Verifique o instalador gerado antes de distribuí-lo.
