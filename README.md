# Coffee Lab

Aplicação web para registrar e explorar o preparo de cafés especiais, reunindo receitas, estoque, extrações, diário sensorial, estatísticas e recursos de IA em um único lugar.

O projeto foi desenvolvido como uma aplicação completa, conectando **frontend, backend, banco de dados, APIs, PWA e Inteligência Artificial**.

## Visão geral

O Coffee Lab nasceu de uma ideia simples: transformar o registro de cada café em um espaço para experimentar, comparar e aprender.

A aplicação permite acompanhar desde o café disponível em estoque até a receita utilizada, os parâmetros de preparo e as percepções sensoriais depois da extração.

## Principais recursos

- Autenticação, perfil e sessão persistente.
- Biblioteca de cafés com busca, filtros, fotos e favoritos.
- Controle de estoque e histórico de movimentações.
- Livro de receitas com etapas, duplicação, compartilhamento e modo guiado.
- Cálculo de café e água a partir do ratio e da quantidade desejada.
- Cronômetro de preparo com registro de extrações.
- Diário sensorial e explorador de perfil sensorial.
- Caderno de bebidas autorais.
- Dashboard com estatísticas e atividade.
- Barista de IA integrado via OpenRouter.
- PWA instalável com recursos offline.
- Cache local e fila para operações realizadas sem conexão.
- Notificações locais.
- Compartilhamento de cafés, receitas, bebidas e extrações em PNG.

## Stack

| Área | Tecnologias |
| --- | --- |
| Backend | Python, FastAPI, SQLAlchemy 2.0, Pydantic 2 |
| Banco de dados | PostgreSQL, NeonDB, Alembic |
| Frontend | HTML5, CSS3, JavaScript Vanilla |
| PWA | Manifest, Service Worker, IndexedDB |
| Visualização | Chart.js |
| Inteligência Artificial | OpenRouter API |
| Desenvolvimento | Git, GitHub, ambiente virtual Python |

## Arquitetura

```text
Coffee Lab
│
├── Backend
│   ├── FastAPI
│   ├── SQLAlchemy
│   ├── Pydantic
│   └── Alembic
│
├── Banco de dados
│   └── PostgreSQL / NeonDB
│
├── Frontend
│   ├── HTML
│   ├── CSS
│   └── JavaScript
│
├── PWA
│   ├── Manifest
│   ├── Service Worker
│   └── IndexedDB
│
└── IA
    └── OpenRouter API
```

## Estrutura principal

```text
.
├── main.py                 # API, rotas e servidor
├── core.py                 # Configurações, banco, modelos e schemas
├── requirements.txt        # Dependências Python
├── alembic.ini             # Configuração Alembic
├── alembic/                # Migrações
├── static/
│   ├── index.html          # Interface principal
│   ├── css/style.css       # Estilos
│   ├── js/app.js           # Lógica da aplicação
│   ├── manifest.json       # Manifest PWA
│   └── icons/              # Ícones
└── sw.js                   # Service Worker
```

## Executando localmente

### 1. Clone o projeto

```bash
git clone https://github.com/vaoliverosdev/coffeeLab.git
cd coffeeLab
```

### 2. Crie o ambiente virtual

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure o ambiente

Crie um `.env` na raiz quando quiser utilizar PostgreSQL/NeonDB ou recursos externos:

```env
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST/DBNAME?sslmode=require
SECRET_KEY=uma-chave-longa-e-segura
OPENROUTER_API_KEY=sua-chave
APP_ENV=development
```

Sem `DATABASE_URL`, o ambiente local pode utilizar SQLite para desenvolvimento.

A chave do OpenRouter só é necessária para o Barista de IA.

Nunca publique chaves ou credenciais no repositório.

### 5. Inicie a aplicação

```bash
uvicorn main:app --reload
```

A aplicação ficará disponível em:

```text
http://localhost:8000
```

Para testar em outro dispositivo da mesma rede:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## PWA e funcionamento offline

O Coffee Lab foi pensado para continuar útil mesmo quando a conexão não está disponível.

A aplicação utiliza:

- App shell em cache.
- Service Worker versionado.
- Navegação offline.
- Persistência local da sessão.
- IndexedDB para dados previamente carregados.
- Fila de operações de escrita realizadas offline.
- Sincronização quando a conexão retorna.
- Proteção contra sincronizações simultâneas.

O Service Worker não intercepta diretamente as rotas de API. O controle de cache e sincronização dos dados da aplicação é feito pela camada de acesso da própria aplicação.

## Banco de dados

O projeto utiliza SQLAlchemy para acesso ao banco e Alembic para evolução controlada do schema.

Comandos úteis:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Deploy

O projeto possui configuração para deploy no Render por meio de `render.yaml` e pode utilizar PostgreSQL hospedado no NeonDB.

Em produção, configure as variáveis de ambiente necessárias e utilize uma `SECRET_KEY` segura. Para recursos de e-mail, login social e IA, configure também suas respectivas credenciais no ambiente de deploy.

## Segurança

O projeto inclui validação de senha, verificação de e-mail, recuperação de senha, controle de sessão, limitação de tentativas em rotas sensíveis e validação de uploads.

Credenciais e configurações sensíveis devem permanecer exclusivamente em variáveis de ambiente.

Para testar em outro dispositivo da mesma rede:

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

Teste automatizado de autenticacao Google:

```bash
python -m pytest tests/test_google_auth.py -q
```

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
  - Sem `GOOGLE_CLIENT_ID`, os botoes do Google ficam ocultos e o login tradicional continua funcionando.
  - O backend valida `aud`, `sub` e `email_verified`, cria conta nova com e-mail verificado e bloqueia vinculos conflitantes.
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

O Coffee Lab está em desenvolvimento ativo, com foco atual em testes gerais, responsividade, PWA instalado, ajustes de produção, documentação e validação antes de uso intensivo.

## Autor

Victor Oliveros

- GitHub: https://github.com/vaoliverosdev
- LinkedIn: https://www.linkedin.com/in/victor-andres-oliveros-p%C3%A9rez-087035382
