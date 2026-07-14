# Contribuindo

Contribuições são bem-vindas por meio de issues e pull requests.

## Ambiente de desenvolvimento

1. Use Windows com Python 3.10 ou superior.
2. Execute `run_debug.bat` para criar o ambiente virtual e abrir o aplicativo com o terminal visível.
3. Faça alterações pequenas e objetivas.
4. Execute os testes antes de enviar uma contribuição:

```powershell
python -m unittest discover -s tests -v
python -m compileall app.py timer_app.py database.py master_database.py csv_store.py csv_reader.py
```

## Diretrizes

- Não envie bancos SQLite, arquivos CSV, logs, pastas de build ou ambientes virtuais.
- Não inclua dados reais de usuários, caminhos internos de rede ou informações corporativas.
- Preserve a compatibilidade com CSVs já existentes.
- Todo registro deve continuar usando UUID para evitar duplicação.
- Alterações no formato do CSV devem incluir migração compatível e teste automatizado.
