# Coffee Lab

Coffee Lab e uma aplicacao web para gerenciar cafes especiais, estoque, receitas, extracoes, diario sensorial, bebidas autorais, estatisticas, PWA offline e um Barista de IA integrado via OpenRouter.

O projeto usa FastAPI, SQLAlchemy 2.0, PostgreSQL/NeonDB e frontend Vanilla HTML/CSS/JavaScript.

## Funcionalidades

- Cadastro, login, recuperacao de senha, perfil, avatar e sessao persistente.
- Biblioteca de cafes com CRUD, fotos, favoritos, busca, filtros e ordenacao.
- Controle de estoque com compras, abertura de pacotes, ajustes e historico de movimentacoes.
- Livro de receitas com etapas, favoritos, duplicacao, compartilhamento e modo guiado.
- Motor inteligente para ratio, agua e cafe.
- Cronometro de preparo com registro automatico de extracao.
- Diario sensorial e explorador de perfil sensorial.
- Caderno de bebidas autorais.
- Barista de IA com historico de conversas.
- Dashboard de estatisticas com Chart.js e calendario de atividade.
- PWA instalavel com app shell offline, cache de GETs e fila de escritas offline.
- Notificacoes locais para hora do cafe, estoque e conquistas.
- Compartilhamento social em PNG para cafes, receitas, bebidas e extracoes.

## Stack

- Python 3.12+
- FastAPI
- SQLAlchemy 2.0
- Alembic
- Pydantic 2
- PostgreSQL/NeonDB
- HTML5, CSS3 e JavaScript Vanilla
- Chart.js
- OpenRouter API

## Estrutura

```text
.
|-- main.py                 # Rotas FastAPI, API e servidor do frontend
|-- core.py                 # Configuracoes, banco, modelos SQLAlchemy e schemas Pydantic
|-- requirements.txt        # Dependencias Python
|-- alembic.ini             # Configuracao Alembic
|-- alembic/                # Ambiente de migracoes
|-- static/
|   |-- index.html          # SPA
|   |-- css/style.css       # Interface
|   |-- js/app.js           # Logica do frontend, offline e PWA
|   |-- manifest.json       # Manifest PWA
|   `-- icons/              # Icones PWA
`-- sw.js                   # Service Worker
```

## Configuracao Local

Crie e ative um ambiente virtual:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Instale as dependencias:

```bash
pip install -r requirements.txt
```

Opcionalmente, crie um arquivo `.env` na raiz para usar NeonDB e recursos externos:

```env
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST/DBNAME?sslmode=require
SECRET_KEY=troque-por-uma-chave-longa-e-segura
OPENROUTER_API_KEY=sua-chave-openrouter
APP_ENV=development
```

Observacoes:

- Sem `.env`, o ambiente local usa SQLite em `coffee_lab_dev.db`.
- Use a connection string do NeonDB em `DATABASE_URL` quando quiser testar com dados reais.
- `OPENROUTER_API_KEY` e necessaria apenas para o Barista de IA.
- Nunca use o valor padrao de `SECRET_KEY` em producao.

## Banco de Dados

O app cria as tabelas automaticamente no startup via SQLAlchemy para facilitar desenvolvimento local. O projeto tambem possui Alembic configurado para evolucao controlada do schema.

Comandos uteis:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Executar

```bash
uvicorn main:app --reload
```

Acesse:

```text
http://localhost:8000
```

Para testar no celular na mesma rede Wi-Fi:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Depois acesse pelo IP do computador, por exemplo:

```text
http://192.168.1.4:8000
```

## Deploy Gratuito

O projeto esta preparado para deploy no Render usando `render.yaml`.

Fluxo recomendado:

1. Crie ou mantenha um banco PostgreSQL no Neon.
2. Copie a connection string do Neon com SSL.
3. Entre no Render e crie um novo Blueprint a partir deste repositorio.
4. Configure as variaveis:
   - `DATABASE_URL`
   - `OPENROUTER_API_KEY`, se quiser usar o Barista de IA
   - `SECRET_KEY`, se preferir definir manualmente
   - `PUBLIC_BASE_URL`, com a URL publica do Render
   - `ALLOWED_ORIGINS`, com a mesma origem publica do app
   - variaveis SMTP, se quiser verificacao de e-mail e recuperacao de senha em producao
   - `GOOGLE_CLIENT_ID`, se quiser ativar login com Google
5. O Render executara:

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Observacoes:

- O plano gratuito do Render e bom para testes e MVP, mas pode dormir quando fica sem acessos.
- Para uso serio em producao, considere migrar para um plano pago pequeno.
- Mantenha o banco no Neon para preservar dados entre deploys.

## PWA e Offline

O app possui:

- Manifest PWA valido.
- Service Worker versionado.
- App shell em cache.
- Navegacao offline.
- Sessao local persistente.
- Cache IndexedDB para requisicoes GET por usuario.
- Fila offline para POST, PUT, PATCH e DELETE de dados da aplicacao.
- Sincronizacao automatica quando a conexao retorna.
- Protecao contra sincronizacoes simultaneas.
- Tratamento de erro temporario e permanente.
- Barista IA bloqueado para novas mensagens offline.
- Historico da IA cacheavel quando carregado previamente.

O Service Worker nao intercepta `/api/`, evitando cache inseguro de autenticacao ou respostas da IA. Dados de API sao controlados por `apiFetch()` em `static/js/app.js`.

Se o app instalado nao atualizar, remova o PWA instalado ou limpe os dados do site no navegador. O Service Worker usa versionamento de cache para facilitar atualizacoes.

## Testes Recomendados

1. Online: criar conta, logar, navegar por todas as secoes e cadastrar dados.
2. Cache offline: abrir cafes, estoque, receitas, extracoes, diario sensorial, explorador, bebidas, estatisticas e historico de IA.
3. Desconectar internet e recarregar a pagina.
4. Confirmar que a sessao permanece ativa e os dados carregados aparecem.
5. Criar/editar/excluir dados offline e verificar o indicador de fila.
6. Reconectar e confirmar sincronizacao, atualizacao da interface e fila vazia.
7. Instalar o PWA em navegador compativel e abrir novamente offline.
8. Testar responsividade em desktop, Android e iOS/Safari.
9. Testar compartilhamento PNG em telas desktop e mobile.
10. Testar notificacoes com permissao concedida e negada.

## Producao

Antes de publicar:

- Configure `SECRET_KEY` forte.
- Restrinja CORS para os dominios reais.
- Use NeonDB com SSL.
- Configure `PUBLIC_BASE_URL` com a URL publica do app, por exemplo `https://coffee-lab.onrender.com`.
- Configure SMTP para verificacao de e-mail e recuperacao de senha:
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USERNAME`
  - `SMTP_PASSWORD`
  - `SMTP_FROM_EMAIL`
  - `SMTP_FROM_NAME`
- Configure `GOOGLE_CLIENT_ID` para ativar login com Google.
- Configure migracoes Alembic reais para o schema atual.
- Uploads de imagem ja possuem limite de tamanho, formato e resolucao.
- O backend envia headers basicos de seguranca e evita expor detalhes internos em erros da IA.
- Teste PWA em Chrome desktop, Android e iOS/Safari.
- Configure variaveis de ambiente no provedor de deploy.

## Autenticacao e Seguranca

O Coffee Lab possui validacao de senha forte, verificacao de e-mail por token, recuperacao de senha por link temporario, troca de senha no perfil, login com Google configuravel e limitacao simples de tentativas em rotas sensiveis.

Em desenvolvimento, quando o SMTP nao estiver configurado e `APP_ENV=development`, a API retorna links de teste para verificacao/reset. Em producao, configure SMTP para que os links sejam enviados por e-mail.

Uploads de avatar e foto de cafe aceitam JPG, PNG e WebP ate 5 MB e 16 megapixels. Arquivos invalidos sao rejeitados antes de serem salvos.

## Monetizacao com Anuncios

O caminho mais comum e Google AdSense, mas a aprovacao depende de conteudo publico original, paginas institucionais e conformidade com politicas.

Antes de solicitar AdSense, recomenda-se ter:

- Dominio proprio.
- Pagina "Sobre".
- Pagina de privacidade.
- Pagina de termos de uso.
- Conteudo publico util, nao apenas uma area privada apos login.
- Navegacao clara e sem telas quebradas no mobile.
- Trafego real minimo para validar engajamento.

Como o Coffee Lab e principalmente uma aplicacao logada, anuncios tendem a funcionar melhor em paginas publicas complementares, como blog, guias de preparo, receitas publicas e landing page. Dentro da area privada, anuncios podem atrapalhar a experiencia e reduzir retencao.

## Status

Fases 0 a 17: implementadas.

Fase 18: em revisao final, com foco em testes gerais, responsividade mobile, PWA instalado, ajustes de producao, documentacao tecnica e validacao antes do uso intensivo.
