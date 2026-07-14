# Checklist de publicação

Antes do primeiro push:

- confira se `icons/` contém apenas o ícone que pode ser publicado;
- não copie `dist/`, `build/`, `.venv/`, `.venv-build/` ou `.build-assets/`;
- não inclua CSVs, SQLite, logs, relatórios Excel, instaladores, ZIPs ou capturas com dados reais;
- revise o nome do autor na licença MIT;
- execute os testes locais;
- gere o instalador em uma cópia limpa do repositório.

## Primeiro commit

```powershell
git init
git add .
git commit -m "feat: publica versão inicial do Timer Task Master"
git branch -M main
git remote add origin <URL-DO-REPOSITORIO>
git push -u origin main
```

## Configuração recomendada no GitHub

- descrição: `Aplicativo Windows para registro de tarefas e gestão de horas com SQLite local e CSV compartilhado.`
- tópicos: `python`, `pyside6`, `windows`, `time-tracking`, `sqlite`, `csv`;
- habilitar Issues;
- manter a branch `main` protegida quando houver mais colaboradores;
- publicar executáveis e instaladores somente em Releases, nunca na raiz do código-fonte.
