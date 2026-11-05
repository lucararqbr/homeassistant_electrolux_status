# electrolux_status — versão modificada

Integração customizada do Home Assistant para aparelhos Electrolux/AEG
(cloud, via `pyelectroluxocp`), com modificações locais para ar-condicionado.

## Versão base

- **Integração:** Electrolux Status (`electrolux_status`)
- **Versão original:** **2.3.6** (campo `version` do `manifest.json`)
- **Repositório original:** https://github.com/albaintor/homeassistant_electrolux_status
  (codeowners: @albaintor, @kingy444)
- **Base no Git:** tag `v2.3.6` do repositório original (remote `upstream`),
  pasta `custom_components/electrolux_status`. Conferido em 01/11/2026: é a
  versão mais recente (após ela o original só tem um commit de workflow de release).
- **Home Assistant alvo:** 2026.10.4

Apesar do nome `_climate_` no zip, a versão original **não** tem plataforma
`climate`; ela foi adicionada nestas modificações.

## Histórico no Git

| Commit | Conteúdo |
|---|---|
| `original v2.3.6` | Arquivos exatos da tag `v2.3.6` do GitHub + `.gitignore`/`.gitattributes` |
| `ajuste anterior: ...` | Item 4 abaixo — já estava no zip `electrolux_status_climate_2.3.6.zip` |
| `minhas modificações` | Conteúdo de `electrolux_status_climate_2.3.6_modificado_r2.zip` (31/10/2026) |
| `ocultar entidades de Configuração por padrão` | Item 9 abaixo (01/11/2026) |
| `docs: CLAUDE.md` | Este arquivo |
| `estado do aparelho e secagem automática como binary sensor` | Item 10 abaixo (03/11/2026) |
| `verificação da API e reconexão do websocket` | Item 11 abaixo; desliga o item 9 (04/11/2026) |
| `testes automatizados` | Pasta `tests/` — ver seção "Testes" (04/11/2026) |
| `renovação do token em fuso negativo (401)` | Item 12 abaixo (04/11/2026) |

Para ver tudo que mudou em relação ao original: `git diff v2.3.6 main` não
funciona direto (a tag tem outra estrutura de pastas); use
`git diff <hash de "original v2.3.6"> main` (hashes em `git log --oneline`)
ou o comparativo no GitHub (abaixo).

**Tag `rodada-1`:** 1ª rodada de modificações (28/10/2026, zip
`_modificado.zip`), guardada fora do `main` como backup. Tinha o climate e as
traduções iniciais, mas não o timer `stopTime`, o `display_step` nem os nomes
de entidade traduzíveis. Ver com `git show rodada-1 --stat`.

Os zips originais foram removidos (enviados para a Lixeira em 01/11/2026);
todo o conteúdo deles está reproduzido nos commits acima, exceto o
`__pycache__` do zip original.

## GitHub

- **Remote `upstream`:** https://github.com/albaintor/homeassistant_electrolux_status
- **Fork (público):** https://github.com/lucararqbr/homeassistant_electrolux_status
  — branch `modificado`: os mesmos commits deste repositório, mas na estrutura
  do original (`custom_components/electrolux_status/`), partindo da tag `v2.3.6`.
- **Comparativo original × modificado:**
  https://github.com/albaintor/homeassistant_electrolux_status/compare/v2.3.6...lucararqbr:homeassistant_electrolux_status:modificado
- Este repositório local tem os arquivos na raiz (estrutura de instalação);
  o branch `modificado` do fork é gerado a partir dele. Ao mudar algo aqui,
  replicar o commit no branch `modificado` e fazer push.

## Modificações em relação ao original

### 1. Entidade `climate` nativa para ar-condicionado
**Arquivos:** `climate.py` (novo), `const.py`, `api.py`

**Por quê:** no original o ar-condicionado aparecia como um monte de entidades
soltas (botões ON/OFF, selects de modo e ventilador, number de temperatura...).
Uma entidade `climate` dá o cartão de termostato no dashboard, funciona com
assistentes de voz e com automações padrão de clima.

- `Platform.CLIMATE` adicionado em `PLATFORMS` (`const.py`).
- Um aparelho é tratado como ar-condicionado quando tem as capabilities `mode`
  e `targetTemperatureC`, e também `fanSpeedSetting` ou `appliance_type == "AC"`.
- As opções são lidas das capabilities da API (não fixas no código), ignorando
  valores marcados como `disabled`:
  - **Modos HVAC:** `OFF` + `AUTO/COOL/DRY/HEAT/FAN_ONLY` conforme o aparelho.
  - **Liga/desliga:** via `executeCommand` ON/OFF. Ao ligar, o aparelho retoma o
    último modo; se for pedido outro modo, ele é enviado 1 s depois.
  - **Temperatura:** atual (`ambientTemperatureC`) e alvo (`targetTemperatureC`),
    com min/máx/passo da capability (padrão 16–30 °C, passo 1).
  - **Ventilador:** `fanSpeedSetting` → `auto/low/medium/high` (+ outros valores
    em minúsculas, p.ex. `turbo`).
  - **Swing:** `flapOscillate` on/off (trata o bug da Electrolux em que alguns
    aparelhos exigem strings `ON`/`OFF` em vez de booleanos).
  - **Presets da aleta:** combinam oscilação + `flapPosition`
    (`oscillate_wide/up/middle/down` e `fixed_up` … `fixed_down`).
- Enquanto o ciclo **Clean Air** (secagem automática) roda, o climate mostra
  `OFF` com ação `DRYING`.
- O nome da entidade é o próprio nome do aparelho (`name = None`).

### 2. Remoção das entidades redundantes com o climate
**Arquivos:** `climate.py` (`covers()`), `api.py`, `const.py`
(`CLIMATE_REMOVE_REDUNDANT_ENTITIES = True`)

**Por quê:** evitar dois controles para a mesma coisa (e automações disparando
por entidades duplicadas). Só são removidas as entidades que o climate
substitui por completo:

- botões `executeCommand` ON/OFF
- number `targetTemperatureC`
- select `fanSpeedSetting`
- select `mode` (só se todos os modos da API forem mapeáveis ou estiverem ocultos)
- switch `flapOscillate`
- select `flapPosition` (só se todas as posições tiverem preset)

### 3. Controles restantes do ar-condicionado vão para "Configuração"
**Arquivos:** `climate.py` (`demote_controls_to_config()`), `api.py`,
`const.py` (`CLIMATE_KEPT_CONTROLS_AS_CONFIG = True`)

**Por quê:** o climate passa a ser o único controle "principal" do aparelho;
switches/selects/numbers/botões que sobram (sleep, som, timer...) ficam na
categoria Configuração, fora dos dashboards automáticos e da voz.

### 4. Regra global de categoria: adicionada antes e depois retirada
**Arquivo:** `api.py` (`get_entity`)

O zip usado como "original" (`electrolux_status_climate_2.3.6.zip`) **não era
idêntico** à v2.3.6 do GitHub: já tinha um ajuste em `api.py` que colocava
**todo** switch, select e number na categoria `EntityCategory.CONFIG`
("Keep only action buttons (ON/OFF) in Controls"). Ele está no commit
`ajuste anterior: ...`.

Na r2 essa regra foi retirada e substituída pelo item 3, que só vale para
aparelhos com climate.

**Resultado em relação à v2.3.6 do GitHub:** nenhuma diferença para aparelhos
**sem** climate (purificador, geladeira etc.) — seus switches/selects/numbers
ficam como no original, sem categoria. Se quiser esses controles também em
Configuração (e ocultos, pelo item 9), reintroduzir a regra para eles.

### 5. Ocultar modos que o modelo não suporta de fato
**Arquivos:** `const.py` (`CLIMATE_HIDDEN_MODES`), `climate.py`

**Por quê:** a API lista `HEAT` para o modelo **YI12F**, que é só frio.
Chave = modelo como aparece na página do dispositivo; valor = modos crus da API
a esconder. Para outro modelo, basta adicionar uma linha.

```python
CLIMATE_HIDDEN_MODES = {"YI12F": ["HEAT"]}
```

### 6. Timer de desligamento (`stopTime`) ajustável de hora em hora
**Arquivos:** `catalog_core.py`, `model.py`, `number.py`

**Por quê:** a API informa o tempo restante em segundos (mostrado em minutos),
mas o aparelho e o app só programam de hora em hora; com o passo da API o
slider permitia valores que o aparelho não aceita.

- Novo item `stopTime` no catálogo: number readwrite, 0–43200 s (0–12 h),
  passo 3600 s, ícone `mdi:timer-outline`.
- Novo campo `display_step` em `ElectroluxDevice` (`model.py`): força o passo do
  slider na unidade exibida.
- `ElectroluxNumber.native_step` (`number.py`) usa `display_step` quando
  definido (aqui, 60 min).

### 7. Nomes de entidades traduzíveis
**Arquivos:** `const.py` (`TRANSLATED_ENTITY_NAMES`), `entity.py`,
`strings.json`, `translations/en.json`

**Por quê:** no original os nomes das entidades eram sempre o texto gerado em
inglês a partir do atributo da API.

- Para os nomes da lista `TRANSLATED_ENTITY_NAMES` (`alerts`, `appliance_state`,
  `auto_sense_mode`, `clean_air_mode`, `comfort_air`, `connectivity_state`,
  `evaporator_defrost_state`, `filter_state`, `sleep_mode`, `sound_volume`,
  `stop_time`), a entidade recebe `translation_key` e o nome vem de
  `entity.<plataforma>.<chave>.name` nos arquivos de tradução.
- Se não houver tradução carregada, mantém o nome gerado; itens do catálogo com
  `friendly_name` continuam com prioridade.
- Seção `entity` adicionada em `strings.json`/`en.json` para todas as
  plataformas, mais os estados do climate (`fan_mode`, `preset_mode`,
  `swing_mode`) sob a chave `electrolux_ac`.

### 8. Traduções PT-BR
**Arquivos:** `translations/pt_br.json`, `translations/pt-BR.json` (novo),
`translations/pt.json`

**Por quê:** interface em português do Brasil.

- Seção `entity` traduzida, com os nomes usados no app/manual do aparelho:
  p.ex. *Secagem automática* (clean air), *Ar indireto* (comfort air),
  *Dormir bem* (sleep), *Som*, *Timer*, *AutoSense*, *Estado do filtro*,
  *Estado do degelo do evaporador*; estados (*Ligado/Desligado*,
  *Em funcionamento*, *Inativo*, *Conectado/Desconectado*...), velocidades
  (*Automático/Baixa/Média/Alta/Turbo*) e presets da aleta
  (*Oscilar: Amplo*, *Fixo: Direcionado para cima*...).
- `pt-BR.json` é cópia idêntica de `pt_br.json`: o Home Assistant usa o código
  de idioma `pt-BR`, então o arquivo com hífen é o que de fato é carregado.
- `pt.json` recebeu a mesma seção `entity` em PT-BR (a parte `config` continua
  em português de Portugal, como no original).

### 9. Opção para ocultar entidades de "Configuração" (desligada)
**Arquivos:** `const.py` (`CONFIG_ENTITIES_HIDDEN_BY_DEFAULT`), `entity.py`
(`entity_registry_visible_default`)

Criada em 01/11/2026 para ocultar por padrão as entidades da categoria
Configuração. **Desligada em 04/11/2026** (`CONFIG_ENTITIES_HIDDEN_BY_DEFAULT =
False`): decidido que as entidades de Configuração **não** precisam ficar
ocultas. O mecanismo ficou no código; para religar, basta trocar para `True`.
Nenhuma entidade chegou a ser ocultada no HA enquanto estava ligada
(conferido no registro de entidades em 04/11/2026).

- Quando ligada, vale para toda entidade com `EntityCategory.CONFIG`: as
  rebaixadas pelo item 3 e as que já vêm do catálogo como CONFIG.
- O Home Assistant só aplica isso quando a entidade é **registrada pela
  primeira vez**. Entidades que já existem mantêm a visibilidade atual; para
  aplicar nelas, ocultar manualmente ou remover e recriar a entidade/integração.
- Entidades ocultas continuam funcionando e podem ser reexibidas em
  Configurações → Entidades.

### 10. Estado do aparelho e Secagem automática como binary sensor
**Arquivos:** `const.py` (`CLIMATE_BINARY_SENSORS`), `api.py` (`get_entity`),
`model.py` (`state_off_values`), `binary_sensor.py`, `strings.json`,
`translations/en.json`, `pt_br.json`, `pt-BR.json`, `pt.json`

**Por quê:** no ar-condicionado esses dois estados eram sensores de texto
(*Em funcionamento / Inativo / Desligado* e *Ligada / Desligada*); como
liga/desliga ficam mais simples para cartões e automações.

- Só vale para aparelhos com climate; nos demais (lavadora etc.)
  `applianceState` continua sensor de texto, como no original.
- `applianceState` → binary sensor classe `power` (*Ligado/Desligado*),
  ícone `mdi:power`, **habilitado por padrão** (no catálogo original vem
  desabilitado).
- `cleanAirMode` → binary sensor sem classe (*Ligada/Desligada*), ícone
  `mdi:water-off`.
- Desligado **só** quando a API informa `OFF`; qualquer outro valor (`RUNNING`,
  `IDLE`, `ON`...) conta como ligado. Novo campo `state_off_values` em
  `ElectroluxDevice` para isso.
- A entrada do catálogo é copiada (`copy.replace`) antes de ser alterada, para
  não mudar a definição usada por outros aparelhos.
- **Ao instalar:** as entidades mudam de domínio (`sensor.*` →
  `binary_sensor.*`). As antigas ficam como "não fornecidas" e podem ser
  excluídas; automações/cartões que usavam `sensor.*` precisam ser ajustados
  (estados agora `on`/`off`).
- Valores declarados pela API (diagnóstico de 03/11/2026): `applianceState` =
  `OFF, RUNNING, IDLE, PAUSED, READY_TO_START, DELAYED_START, END_OF_CYCLE,
  ALARM` (lista genérica Electrolux); na prática os ar-condicionados só usam
  `OFF`/`RUNNING` (10 dias de histórico). `cleanAirMode` = `ON/OFF` (quando
  `ON`, a API aceita o comando `OFF` para interromper a secagem — não usado).

### 11. Verificação da API e reconexão do websocket sem recarregar
**Arquivos:** `coordinator.py` (`async_check_api`, `reconnect_websocket`,
`_fetch_appliances_list`), `__init__.py`, `button.py`
(`ElectroluxReconnectButton`), `api.py`, `const.py` (`API_CHECK_INTERVAL`,
`API_CHECK_IGNORED_KEYS`, `TRANSLATED_ENTITY_NAMES`), traduções

**Por quê:** de vez em quando os estados congelavam e era preciso recarregar a
integração. A integração só recebe dados pelo websocket (não faz consulta
periódica), e a renovação automática dele (a cada 12 h, criada para as issues
#27/#35 do original "doesn't update states after a few hours") está
**comentada no original** desde 2024. Se a Electrolux para de mandar eventos
sem fechar a conexão, nada percebe.

- **A cada 10 min** (`API_CHECK_INTERVAL = 600`): uma chamada
  `get_appliances_list` traz o estado de todos os aparelhos e é comparada com o
  do HA (só valores simples; ignora contadores `startTime`/`stopTime`/
  `timeToEnd` e valores aninhados).
  - Diferenças são aplicadas na hora.
  - Se houve diferença **e** o websocket não mandou nada nesse intervalo, o
    websocket é **reconectado** (entidades mantidas, sem recarregar). Fica no
    log como aviso: `Electrolux websocket stopped sending updates ...
    reconnecting`.
  - HTTP 401/403: refaz o login e tenta de novo.
- **Botão "Reconectar API"** (um por aparelho, categoria Configuração, sempre
  disponível): faz a verificação e força a reconexão.
- A reconexão cancela a tarefa do websocket anterior antes de abrir outra (sem
  isso, dois loops de conexão da biblioteca podem rodar juntos).
- ~144 chamadas/dia à API.
- **Não testado com a falha real** — conferir no log do HA se aparece o aviso de
  reconexão e se os estados deixam de congelar.

### 12. Renovação do token corrigida para fusos negativos (erro 401)
**Arquivos:** `coordinator.py` (`async_refresh_token`,
`_execute_command_with_relogin`, `token_renewal_task`, `_fetch_appliances_list`,
`async_check_api`)

**Sintoma:** de vez em quando os comandos falhavam com
`401, message='Unauthorized', url='.../appliances/<id>/command'` e só voltavam
recarregando a integração; o botão "Reconectar API" (item 11) não resolvia.

**Causa (bug do original):** para renovar o token 5 min antes de vencer, o
`token_renewal_task` marcava o token como "vencido há 10 min" usando horário
**UTC sem fuso**, mas a biblioteca `pyelectroluxocp` compara com
`datetime.now()` (**horário local** sem fuso). Em UTC−3 (America/Fortaleza),
"UTC − 10 min" fica 2h50 **no futuro** → a biblioteca não renovava, o token
vencia e todos os comandos davam 401 por ~3 h, até a biblioteca renovar
sozinha. Na Europa (UTC+) o bug não aparece. Confirmado em 04/11/2026: token
salvo em `.storage/electrolux_status` emitido às 08:13, vencido às 20:13 e não
renovado.

- `async_refresh_token()`: marca o vencimento em horário local
  (`datetime.now()`) e refaz o login; se o refresh token for recusado, faz
  login completo com usuário e senha. Usado pela renovação automática, pela
  verificação da API (401/403) e pelo botão "Reconectar API" (que agora também
  renova o token).
- Comandos (climate, botões, switches, selects, numbers): em 401 o token é
  renovado e o comando é **repetido uma vez**. Feito envolvendo
  `client.execute_appliance_command` no construtor do coordinator, então vale
  para todas as entidades. Fica no log como aviso:
  `Electrolux command rejected (HTTP 401), renewing the token and retrying`.
- O teste `test_refresh_token_marks_token_expired_for_the_library` reproduz o
  bug (falha com o código antigo) quando roda num computador em fuso negativo,
  como este.

## Arquivos não alterados

`catalog_purifier.py`,
`catalog_refrigerator.py`, `config_flow.py`,
`diagnostics.py`, `manifest.json` (continua 2.3.6), `select.py`, `sensor.py`,
`switch.py`, `util.py`, `appliance_definitions/`, demais traduções.

## Instalação no Home Assistant

1. Acessar o `/config` do Home Assistant via **Samba** ou **SSH**.
2. Copiar os arquivos da integração para
   `/config/custom_components/electrolux_status/`
   (o nome da pasta precisa ser `electrolux_status`, igual ao `domain`).
   **Não** copiar `.git/`, `tests/`, `.gitignore`, `.gitattributes`,
   `CLAUDE.md` nem os `*.zip`.
   - **Via Samba** (usado aqui: `Z:\custom_components` = `/config/custom_components`),
     no PowerShell a partir desta pasta; depois apagar
     `Z:\custom_components\electrolux_status\__pycache__`:
     `robocopy . "Z:\custom_components\electrolux_status" /E /XD .git tests .pytest_cache /XF CLAUDE.md .gitignore .gitattributes`
   - Via SSH, a partir desta pasta:
     `git archive HEAD | ssh root@<ip-do-ha> "mkdir -p /config/custom_components/electrolux_status && tar -x -C /config/custom_components/electrolux_status --exclude=CLAUDE.md --exclude=.gitignore --exclude=.gitattributes --exclude=tests"`
3. Se já existia uma versão instalada (p.ex. via HACS), substituir os arquivos;
   apagar o `__pycache__` antigo da pasta se houver.
4. **Reiniciar o Home Assistant** (Configurações → Sistema → Reiniciar).
5. Se for a primeira instalação: Configurações → Dispositivos e serviços →
   Adicionar integração → *Electrolux Status*.
6. Após reiniciar, conferir no aparelho de ar-condicionado se a entidade
   `climate.*` apareceu e se as entidades redundantes antigas sumiram (as que
   ficaram órfãs no registro podem ser removidas manualmente).

> Atenção: se a integração estiver instalada pelo HACS, uma atualização pelo
> HACS sobrescreve estas modificações.

## Testes

Pasta `tests/` (não vai para o HA). Testam as modificações com o Home Assistant
real, sem precisar do servidor nem da nuvem Electrolux:

- `tests/test_electrolux.py`: criação das entidades a partir dos dados reais
  dos dois ar-condicionados (climate, binary sensors, botão Reconectar API, IDs
  únicos), regra liga/desliga, traduções e a verificação da API / reconexão do
  websocket com a nuvem simulada (item 11).
- `tests/fixtures/diagnostics_ar_condicionado.json`: parte `appliances_*` do
  diagnóstico do HA de 03/11/2026 (Ar SALA YI22F, Ar HOME OFFICE YI12F), sem
  dados da conta e com números de série fictícios — o fork é público. Ao
  atualizar com um diagnóstico novo, manter essa limpeza.
- `tests/requirements.txt`: mesmas versões do servidor (HA 2026.10.4,
  `pyelectroluxocp` 0.1.3).

Python 3.14 instalado no Windows (04/11/2026, via `winget install
Python.Python.3.14 --scope user`). Ambiente em
`C:\Users\conta\.venvs\electrolux_status` — fora do OneDrive (o HA tem
centenas de MB) e fora da AppData (o app Claude redireciona o que ele cria lá
para o armazenamento do próprio app). Criar uma vez:

```bash
py -3.14 -m venv "$HOME/.venvs/electrolux_status"
"$HOME/.venvs/electrolux_status/Scripts/python.exe" -m pip install -r tests/requirements.txt
```

Rodar, a partir desta pasta (o `-P` é obrigatório: o `select.py` da integração
esconderia o módulo `select` do Python):

```bash
"$HOME/.venvs/electrolux_status/Scripts/python.exe" -P -m pytest -p no:cacheprovider tests
```

Rodar os testes antes de cada cópia para o HA. Eles **não** cobrem o
comportamento contra a nuvem real (p.ex. se o websocket volta a mandar dados).

## Atualizando para uma nova versão do original

1. Baixar a nova versão do repositório original e salvar o zip aqui como backup.
2. Criar um branch a partir do commit `original v2.3.6`, substituir os arquivos
   pelos da nova versão e commitar como `original vX.Y.Z`.
3. Fazer rebase/merge de `minhas modificações` sobre esse commit, resolvendo
   conflitos (principalmente `api.py`, `const.py`, `entity.py`, traduções).
4. Atualizar este arquivo com a nova versão base.

## Regras do projeto

- Textos e traduções em PT-BR.
- Entidades auxiliares/redundantes ficam na categoria Configuração, mas
  **visíveis** (decisão de 04/11/2026; não seguir a regra geral de ocultar).
- Documentar sempre a versão original usada como base.
