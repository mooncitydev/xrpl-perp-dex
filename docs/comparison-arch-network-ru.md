# Чем мы отличаемся от Arch Network

**Аудитория:** техническая команда, инвестор и любой, кого спросили "а чем вы отличаетесь от Arch?".
**Статус:** конкурентное и архитектурное сравнение. Bilingual: английская версия в `comparison-arch-network.md`.
**Контекст:** Arch Network (`book.arch.network`) — это Bitcoin-native execution платформа, shipping'нувшая в testnet раньше нас, и теперь это дефолтная точка сравнения каждый раз, когда мы описываем BTC-ориентированную версию нашего собственного продукта. Этот документ существует, чтобы ответить на вопрос "чем это отличается от Arch?" точно и честно — не пренебрежительно, потому что Arch реален и за ним реальная инженерия, и не защищаясь, потому что эти два проекта на самом деле делают разные вещи.

Короткая версия: **Arch — это платформа, мы — продукт**. Они продают инфраструктуру разработчикам, которые хотят строить Bitcoin-native DeFi приложения; мы продаём единственный hardware-attested perp DEX напрямую трейдерам. Overlap узкий, trust-модели разные, и конкурент, за которым надо наблюдать на Arch, — это не сам Arch, а **VoltFi**, их экосистемный derivatives-проект. Остаток документа это разворачивает.

---

## 1. Executive summary

- **Arch Network — это general-purpose execution платформа для Bitcoin.** Они shippают eBPF-based VM (ArchVM), dPoS валидаторский сет, стейкающий нативный токен, FROST+ROAST threshold signing для settlement'а в Bitcoin, и Rust SDK для написания программ. Их экосистема уже включает DEX (Saturn), lending (Autara), derivatives-проект (**VoltFi**) и другие — все как tenants на их платформе.
- **Мы — single-purpose hardware-attested perp DEX.** Matching, risk и custody живут внутри SGX-энклейвов, чей бинарь воспроизводимо собран, а `MRENCLAVE` публично attested. Custody — FROST 2-of-3 через трёх именованных операторов. Нет токена, нет VM, нет tenants — вся система это один аудируемый продукт.
- **Trust-модели разные, ни одна строго не лучше.** Arch security покоится на dPoS валидаторском сете с BFT-гарантиями (f < n/3) и экономических стимулах через slashing стейка — классическая crypto-economic конструкция. Наша покоится на SGX hardware attestation + FROST threshold custody + маленьком, именованном, hardware-key-gated operator-сете. Это разные risk-профили, привлекательные для разных пользователей и контрагентов.
- **Мы не конкурируем с Arch; мы overlap'имся с VoltFi.** Arch — инфраструктура. Проект на Arch, который таргетирует того же конечного пользователя, что и мы, — это VoltFi. Это и есть реальное конкурентное сравнение, и оно архитектурно хорошо для нас: меньший TCB, hardware-attested execution, нет token risk, нет platform dependency.
- **Существование Arch — положительный сигнал для нашего thesis'а.** Независимая команда пришла к тому же примитиву (FROST threshold Schnorr поверх Taproot для non-custodial Bitcoin settlement), который наш signing stack уже shipping'ает. Выбор FROST как базового механизма теперь market-validated.
- **Deploy нашего perp DEX *на* Arch технически возможен, но стратегически неправилен.** Это обменяло бы наш сильнейший differentiator (hardware-attested execution, minimal TCB) на зависимость, которая нам не нужна (мы уже имеем FROST 2-of-3 custody своего собственного).

---

## 2. Что такое Arch Network на самом деле

Важно аккуратно описать Arch перед тем, как сравнивать, потому что много существующего "Bitcoin L2 vs. X" дискурса путает категории. На основе их официального book'а, whitepaper'а и сторонних технических обзоров, Arch состоит из:

- **ArchVM** — виртуальная машина, форкнутая из eBPF-рантайма, который использует Solana, расширенная custom syscalls, которые читают и пишут Bitcoin UTXO state и могут постить транзакции напрямую в Bitcoin. Программы пишутся на Rust и компилируются в eBPF байткод, затем деплоятся на платформу. Это general-purpose execution environment, а не single-application codebase.
- **Децентрализованный валидаторский сет под delegated proof-of-stake.** Валидаторы стейкают Arch native token, отбираются в leader slots по весу стейка, исполняют программы и достигают consensus'а. Валидаторский сет сейчас permissioned — whitelist enforced'ится во время DKG ceremony — с заявленным roadmap'ом к permissionless участию.
- **FROST + ROAST threshold Schnorr signing как settlement primitive.** FROST производит агрегированные BIP340 Schnorr подписи над t-of-n threshold валидаторского сета; ROAST расширяет FROST асинхронным оперированием, так что валидаторы могут входить/выходить между эпохами без остановки consensus'а. Threshold конфигурируем, но их messaging называет "51%+" как majority-honest предположение. Вывод on-chain — это одна BIP340 Schnorr подпись, неотличимая от key-path Taproot расхода.
- **Прямой Bitcoin settlement через Taproot.** Пользователи взаимодействуют с Arch программами через Taproot адреса; валидаторский сет агрегирует подписи и постит результирующие транзакции в Bitcoin mainnet. Нет bridge, нет sidechain, нет wrapped BTC. С точки зрения settlement'а это по-настоящему Bitcoin-native.
- **Sub-second pre-confirmations.** До того, как Bitcoin финализирует транзакцию (десять минут или больше), Arch предлагает более мягкую "pre-confirmation" гарантию от валидаторского сета — валидаторы подписали результат и submit'ят его, когда условия позволят.
- **Нативный токен**, используемый для стейкинга, валидаторского отбора и (предположительно) gas metering исполнения программ. Специфика токеномики — не предмет этого документа, но это имеет значение: Arch экономически — это классический токенизированный L1-на-BTC.
- **Экосистема уже в полёте на testnet.** Именованные проекты включают Saturn (DEX), Autara (lending), **VoltFi (derivatives и perps)**, Ordeez (BNPL), HoneyB (RWAs) и indexing слой Titan для отслеживания mempool и поддержки Runes.

Заметьте, что Arch **не** использует: trusted execution environments. Нет SGX, нет TDX, нет enclave measurement, нет hardware attestation. Вся их модель безопасности — криптографическая (threshold Schnorr) плюс экономическая (стейкинг + slashing) плюс consensus-теоретическая (Byzantine fault tolerance с f < n/3). Это легитимная и хорошо понятная конструкция, и она отличается от нашей по фундаментальной оси. Ни одна конструкция не является заменой другой.

---

## 3. Side-by-side архитектура

Следующая таблица — наиболее чистый способ увидеть, где эти два проекта реально отличаются, без редакционного spin'а ни в одну сторону.

| Ось | Arch Network | Наш проект |
|---|---|---|
| **Класс системы** | General-purpose execution платформа | Single-purpose perp DEX |
| **Единица деплоя** | Rust → eBPF байткод, деплоится любым разработчиком | Наш собственный C++ код внутри SGX энклейва, деплоится нами |
| **Корень доверия** | dPoS + FROST/ROAST + экономический стейк | SGX hardware attestation + FROST 2-of-3 + hardware-key operator ceremony |
| **Operator/validator сет** | n валидаторов, BFT под f < n/3, permissioned сейчас, permissionless в roadmap | 3 именованных оператора, permissioned by design |
| **Consensus** | Да — классический BFT через ROAST над валидаторским сетом | Нет. Matching идёт в одном энклейве; FROST подписывает только settlement-транзакции, не каждый переход состояния |
| **Replicated execution** | Да (все валидаторы исполняют и сравнивают) | Нет (один энклейв исполняет; attestation + FROST settlement — это то, что держит его подотчётным) |
| **Хранение state** | Off-chain в валидаторах, периодически anchored в Bitcoin | SGX-sealed внутри энклейва, не реплицируется |
| **Programmability** | Открытая — любой разработчик может деплоить | Закрытая — только наш собственный код, и это свойство, а не ограничение |
| **Native token** | Да — используется для стейкинга, gas, валидаторского отбора | Нет |
| **Latency matching'а** | Sub-second pre-confirmation, финал на Bitcoin confirmation | Микросекунды внутри энклейва, settlement в Bitcoin на confirmation |
| **Custody механизм для BTC** | FROST threshold Schnorr агрегированный через валидаторский сет | FROST 2-of-3 Schnorr агрегированный через три SGX энклейва |
| **TEE / hardware attestation** | Не используется ни на одном слое | Центральный элемент дизайна |
| **Аудируемый бинарь с криптографическим доказательством того, что запущено** | Нет — consensus этого не даёт | Да — `MRENCLAVE` публично attested через DCAP |
| **Категория конкурента для трейдеров** | DEX — это Arch, но продукт, конкурирующий за того же трейдера, — это **VoltFi** | Мы конкурируем напрямую с VoltFi и с централизованными BTC-perp venues (BitMEX, Deribit) |
| **Категория конкурента для разработчиков** | Arch конкурирует с Solana, Ethereum, другими smart-contract платформами | Мы не конкурируем за разработчиков — мы не хостим разработчиков |
| **Platform risk для нас, если бы мы её использовали** | Мы бы стали tenants, exposed'ными к Arch VM багам, liveness валидаторов, Arch token economics, Arch governance | Ноль — мы владеем и оперируем полным стеком |

---

## 4. Сравнение trust-модели — ключевое различие

Это самая важная секция для разговора с инвестором, потому что это место, где два подхода фундаментально расходятся.

### 4.1 Что Arch просит пользователя доверить

- Что большинство валидаторского сета останется честным. С f < n/3 BFT предположением и n валидаторами, пользователю нужно, чтобы n/3 или больше stake-weighted валидаторского сета оставалось честным для liveness, и n/3 или больше — чтобы предотвратить злонамеренный consensus. Экономический стейк обеспечивает стимул: валидаторы, ведущие себя плохо, теряют свой стейк, поэтому рациональный атакующий должен рисковать большим капиталом, чем может извлечь.
- Что ArchVM корректно исполняет Rust программы, скомпилированные в eBPF, детерминистически, через всех валидаторов. Любая consensus divergence, вызванная VM non-determinism'ом, — это protocol-level failure.
- Что конкретное приложение на Arch (например, VoltFi для perps) реализовано корректно на Rust. Application баги — это риск пользователя, а не Arch.
- Что команда Arch не rug'нет сеть через изменения whitelist'а валидаторов или governance-атаки, пока сеть всё ещё permissioned.
- Что собственная finality Bitcoin'а держится для anchored settlement'а, но этот риск одинаков для любого, кто сеттлится в Bitcoin.

Это **crypto-economic trust модель с большим anonymity set** — пользователю не надо знать ни одного конкретного валидатора, только что распределение стейка широкое и что рациональные стимулы будут держать большинство честным. Это та же конструкция, которую используют Ethereum, Cosmos и Solana, применённая к Bitcoin settlement'у.

### 4.2 Что мы просим пользователя доверить

- Что Intel SGX не сломан катастрофически. "Сломан катастрофически" означает, что master key утёк, или обнаружена remote side-channel атака, которая не требует физического обладания машиной. Ни того, ни другого не случилось за десятилетие существования SGX на server Xeon, и наше обсуждение side-channels в Part 1 `sgx-enclave-capabilities-and-limits.md` объясняет, почему опубликованные атаки требуют лаборатории или полностью скомпрометированного хоста, а не remote exploit'а.
- Что `MRENCLAVE`, который мы публикуем, — это действительно measurement бинаря энклейва, с которым пользователь взаимодействует. Это криптографически верифицируется через DCAP attestation. Это не требует доверия — это доказательство.
- Что двое из трёх наших именованных операторов не сговорятся, чтобы подписать мошеннический вывод. FROST 2-of-3 означает, что компрометация одного оператора оставляет средства в безопасности; два сговорившихся оператора могут подписать, но это именованные персоны под hardware-key ceremony с audit trail. Это small-set, identity-based trust assumption, а не анонимный.
- Что operator deployment ceremony в `deployment-procedure.md` честно соблюдается как минимум двумя операторами. Процедура спроектирована так, что одностороннее отклонение видно другим операторам.
- Что код нашего энклейва свободен от багов, или по крайней мере что баги найдены и исправлены через аудит. Этот риск идентичен для любой программной системы, включая Arch/VoltFi — это не структурный недостаток.

Это **hardware-rooted trust модель с маленьким identity set** — пользователь знает, кто операторы, может проверить, какой код они запускают, и полагается на hardware-гарантии от конкретного CPU-вендора плюс threshold-криптография через именованных участников.

### 4.3 Какая модель "лучше"?

Ни одна строго не лучше. Они оптимизируют за разное:

- **Модель Arch лучше для пользователей, которые предпочитают большие anonymity sets и crypto-economic децентрализацию**. Для идеологически crypto-native пользователя, который считает "три именованных оператора" централизационным red flag независимо от hardware attestation, Arch — более привлекательный вариант.
- **Наша модель лучше для пользователей и контрагентов, которые хотят аудируемого исполнения и минимального TCB**. Для институционального пользователя, регулятора, compliance-офицера или трейдера, который хочет криптографически проверить, что matching и risk logic запускают именно тот код, который они думают, — мы более привлекательный вариант. Arch просто не предлагает эту гарантию, потому что consensus её не даёт — "валидаторы согласились" не то же, что "вот хеш точного бинаря, который произвёл этот результат".
- **Модель Arch имеет больший long-term decentralization ceiling**. Если permissionless roadmap Arch удастся и они достигнут валидаторского сета, сравнимого с Solana или Cosmos, их распределение доверия по-настоящему больше, чем наше когда-либо может быть с тремя операторами.
- **Наша модель имеет гораздо меньший attack surface сегодня**. Наш TCB — это примерно 5000 строк аудированного C++ плюс `libsecp256k1` плюс SGX SDK. TCB Arch — это ArchVM (форк eBPF с custom syscalls) плюс полный validator node software плюс конкретное приложение, запущенное на нём (например, Rust код VoltFi). По строчному счёту и по числу слоёв реализации наш TCB примерно на порядок меньше.

Это разные продукты, обслуживающие разные сегменты того же рынка.

---

## 5. Где Arch объективно впереди нас

Сказано честно, потому что этот документ существует, чтобы выдержать критику:

- **General-purpose programmability.** Они запускают полную VM; любой может задеплоить приложение. Мы — нет и не будем, если только не изменим фундаментально то, чем являемся.
- **Permissionless roadmap.** У них credible путь к по-настоящему децентрализованному валидаторскому сету. У нас нет — три энклейва это три энклейва, и нет cryptoeconomic причины для существования четвёртого.
- **Ecosystem momentum на testnet.** Несколько именованных команд уже строят на Arch (Saturn, Autara, VoltFi, Ordeez, HoneyB). У нас ровно один продукт: наш.
- **Нет зависимости от hardware-вендора.** Arch не зависит от Intel или любого другого кремниевого вендора. Если Intel shipping'нет catastrophic SGX уязвимость или решит discontinue SGX раньше, чем сейчас объявлено, у нас platform problem; у Arch нет.
- **Token-driven growth flywheel.** У них native token, что (к лучшему или к худшему) даёт им механизм для инсентивизации validator participation, bootstrapping ликвидности и награды early ecosystem builders. У нас — нет, by design, и это разговор с инвестором отдельно.
- **Press и narrative position.** "Bitcoin programmability" — это хорошо сформированный investor narrative, который Arch уже claimed. Мы оперируем в более узкой нише ("hardware-attested BTC perp DEX"), которая менее знакома и требует больше объяснений.

Ни один из этих пунктов не является технической deficiency в нашей архитектуре. Это структурные последствия того, что мы построили единый продукт, а они построили платформу, и структурные последствия разных trust-моделей.

---

## 6. Где мы объективно впереди Arch (конкретно по сравнению с VoltFi на Arch)

Тоже честно:

- **Меньший TCB.** Наш trusted code — это бинарь нашего энклейва; их — ArchVM плюс полное validator node software плюс Rust программа VoltFi. Меньше движущихся частей означает меньше мест, где уязвимость может спрятаться, и меньше аудиторов, нужных для покрытия системы.
- **Криптографически верифицируемый бинарь.** Пользователь нашего perp DEX может проверить `MRENCLAVE` через DCAP attestation и подтвердить, что биржа запускает ровно ту версию, которую мы опубликовали. Пользователь VoltFi на Arch не может получить эквивалентного криптографического доказательства — лучшее, что он может, — это "consensus согласен с результатом", что является утверждением о согласии, а не о том, какой код произвёл результат.
- **Нет token risk.** Нет token unlock schedule, нет риска коллапса цены токена, нет риска governance capture, нет регуляторной неопределённости, является ли наш токен security. Fee деноминированы в settlement asset'е (RLUSD на XRPL сегодня, BTC на Bitcoin завтра).
- **Latency matching'а ниже на порядки.** Наш matching engine работает на скорости памяти внутри энклейва — микросекунды на ордер. Sub-second pre-confirmation Arch — это latency валидаторского кворума, что на два-три порядка медленнее. Для maker-taker dynamics, market-making стратегий и high-frequency трейдеров это существенно и измеримо.
- **Известные операторы под документированной ceremony.** Для институционального контрагента, который требует знания того, кто оперирует систему и как подписываются релизы, наша модель это предоставляет. Анонимный валидаторский сет — нет.
- **Ноль platform dependency.** Мы владеем и оперируем весь стек. Нет Arch team upgrade, который может нас забрикировать, нет Arch governance vote, который может изменить наши fee, нет Arch validator liveness проблемы, которая может остановить наш matching.
- **Немедленная BTC-готовность signing слоя.** Наш энклейв уже shipping'ает ровно те криптографические примитивы, которые нужны BTC (BIP340 Schnorr, MuSig2, FROST 2-of-3), независимо от Arch. Мы не ждали, пока платформа станет доступна; мы встроили примитивы в наш собственный энклейв, и аргумент BTC feasibility (`btc-perp-dex-feasibility.md`) стоит сам по себе без ссылки на Arch.

Это и есть genuine competitive ground против VoltFi. Это также ground, на котором наш pitch трейдерам и институциональным контрагентам сильнее всего.

---

## 7. Могли бы мы задеплоить наш perp DEX на Arch вместо оперирования собственной инфраструктуры?

Этот вопрос всплывёт, потому что на поверхности он выглядит привлекательно — "зачем оперировать тремя энклейвами, когда Arch уже предоставляет FROST custody и deployment платформу?" Честный ответ состоит из трёх частей.

**Первое, это технически возможно.** Наш margin engine, liquidation logic, CLOB matching и position state machine в основном portable C++. Переписывание их как Rust программы, таргетирующей ArchVM, — это multi-month инженерная задача, но не research проект. Мы могли бы, в принципе, стать tenant'ом на Arch рядом с VoltFi.

**Второе, это стоило бы нам каждого технического differentiator'а, который у нас сейчас есть.** Мы бы потеряли:
- Hardware-attested execution (ArchVM не SGX; нет `MRENCLAVE` на задеплоенной Arch программе).
- Микросекундный matching latency (мы бы были ограничены валидаторским pre-confirmation временем Arch).
- Минимальный TCB (мы бы унаследовали ArchVM + validator node software + TCB нашего собственного Rust кода).
- Zero-token-dependency fee модель (мы бы платили gas в Arch native токене, с каким бы то ни было economic risk'ом, который это несёт).
- Независимость от platform-governance процесса, который мы не контролируем.

В обмен мы бы получили:
- Не нужно запускать три энклейва на трёх машинах (что мы и так уже настроены делать).
- Доступ к composability Arch с Saturn, Autara и другими Arch-native приложениями (что ценно только если мы хотим быть Arch-ecosystem citizen'ами, и что добавляет coupling risk).
- Permissionless-roadmap story, которую Arch продаёт crypto-native пользователям (которую мы сейчас не пытаемся продавать, потому что наше value proposition другое).

**Третье, trade стратегически неправильный для нас конкретно.** Value proposition платформы Arch её tenants — это "мы предоставляем FROST custody и secure execution environment, так что вам не надо строить их самим". Но *мы уже построили их*. FROST 2-of-3, DKG, MuSig2, Schnorr, Taproot signing — всё это shipping'ается в нашем энклейве сегодня. Платить стоимость tenancy, чтобы получить сервис, который у нас уже есть, — плохой trade. Мы ровно та команда, для которой platform offer Arch наименее ценен, именно потому, что наша собственная signing и custody инфраструктура уже завершена.

Правильный framing для любого разговора на эту тему: **Arch — хороший выбор для команды, которая хочет строить BTC приложение и не хочет оперировать custody инфраструктуру. Мы не эта команда. У нас есть custody инфраструктура. Предложение Arch адресовано другому клиенту, не нам.**

---

## 8. Кто на самом деле конкурент

Arch — это инфраструктура; VoltFi — это derivatives приложение на Arch. Если трейдер решает, что он хочет открыть BTC perp позицию в non-custodial манере завтра, его реалистичные опции:

1. Централизованная биржа (BitMEX, Deribit, Binance, OKX, Bybit). Non-custodial: нет.
2. Wrapped-BTC DeFi perp на Ethereum/Arbitrum/Solana (GMX, Hyperliquid, Drift). Non-custodial: да, но с bridge и wrapping риском.
3. **VoltFi на Arch.** Non-custodial: да, через FROST+ROAST валидаторский сет Arch и прямой Bitcoin settlement. Trust: crypto-economic, большой anonymity set.
4. **Мы, когда наша BTC версия shipping'нется.** Non-custodial: да, через FROST 2-of-3 через три SGX энклейва и прямой Bitcoin settlement. Trust: hardware-attested, маленький identity set.

Опции 3 и 4 обе — "decentralized, L1-native, non-custodial BTC perp DEX" — та же категория. Они отличаются trust моделью, latency и гарантиями исполнения по линиям, которые этот документ изложил. Трейдер рационально выберет между ними на основе того, какой trade-off соответствует его собственным предпочтениям:

- Crypto-purist трейдер, который ценит permissionlessness и не принимает никакого hardware-vendor trust'а → VoltFi.
- Институциональный контрагент, high-frequency трейдер или пользователь, который хочет криптографического доказательства integrity исполнения → мы.

Оба — легитимные предпочтения. Оба соответствуют реальным рыночным сегментам. Рынок на L1 BTC достаточно большой, чтобы оба продукта coexist'или и росли без прямого каннибализирования друг друга, и успех ни одного не исключает успеха другого.

Это важная positioning точка для разговора с инвестором. **Правильное сравнение — это мы vs. VoltFi, а не мы vs. Arch**, и это сравнение, которое мы можем сделать уверенно на технических осях, которые имеют значение.

---

## 9. Почему существование Arch — позитивный сигнал для нашего thesis'а

Рефлекторное прочтение "хорошо фондированная команда shipping'нула Bitcoin execution платформу раньше нас" — это competitive threat. Правильное прочтение — market validation. Конкретно:

- **FROST над Taproot теперь market-validated как правильный custody примитив для non-custodial BTC приложений.** Две независимые команды (наша и Arch) пришли к тому же техническому заключению. Наш собственный signing stack уже shipping'ает это. Тот факт, что Arch выбрал его для своего platform consensus слоя, — подтверждение того, что примитив серьёзен и что builders ему доверяют.
- **Категория "decentralized, L1-native, non-custodial BTC perp DEX" теперь признанная категория.** До того, как Arch + VoltFi существовали, это был аргумент, который мы должны были делать с нуля любому инвестору, который никогда о нём не слышал. Теперь это ecosystem narrative с именованными проектами. Наша работа становится дифференциацией внутри категории, а не изобретением категории.
- **Рынок продемонстрировал готовность фондировать категорию.** Arch фондирован, их экосистема фондирована, VoltFi фондирован. Это прямое доказательство того, что за thesis'ом "BTC programmability для derivatives" стоит capital backing и user interest. Наш fundraising разговор становится легче, а не тяжелее, потому что мы можем указать на reference deal структуру.
- **У нас есть другой и defensible wedge.** Наш TCB меньше, наше исполнение hardware-attested, наш matching быстрее, наша trust модель более читаема институциональным контрагентам. Это реальные differentiators в категории, которую Arch уже легитимизировал.

Виденное так, shipping Arch первыми — строго хорошо для нас: они создали рынок, а мы продаём premium продукт внутри него.

---

## 10. Рекомендация и positioning

Для внутренней стратегии:

- **Не относиться к Arch как к конкуренту для reference'а.** Относиться к VoltFi как к конкуренту для reference'а. Когда потенциальный пользователь или инвестор спрашивает про "сравнение с Arch", мягко поправляем framing на "сравнение с VoltFi" и затем выигрываем на специфике из §4 и §6.
- **Не деплоить наш perp DEX на Arch.** Trade стратегически неправильный для нашей конкретной команды и архитектуры, по причинам в §7.
- **Держать codebase chain-agnostic** через `ChainAdapter` интерфейс, описанный в `btc-perp-dex-feasibility.md`. Это оставляет BTC трек открытым без любого преждевременного commitment'а.
- **Рассмотреть limited interoperability позже.** Если в какой-то момент станет ценно иметь нашу BTC версию, *также* принимающую депозиты от пользователей, держащих позиции в Arch-native активах (Runes, Ordinals и т.д.), это integration уровня оркестратора — reader для Arch state'а, bridge-like адаптер — что не требует становиться tenant'ом на Arch. Это future option, а не near-term задача.

Для разговора с инвестором, однопараграфный ответ на "чем это отличается от Arch?":

> *Arch Network — это general-purpose execution платформа для Bitcoin, построенная на dPoS валидаторском сете с FROST threshold signing и нативным токеном. Их экосистема включает derivatives-проект под названием VoltFi, который конкурирует за того же конечного пользователя, что и мы. Мы не платформа; мы единственный hardware-attested perp DEX. Наш matching и risk engine работает внутри SGX энклейвов, чей бинарь публично attested через MRENCLAVE, custody — FROST 2-of-3 через трёх именованных операторов с документированной hardware-key ceremony, и нет токена. По сравнению с VoltFi на Arch, наш trusted computing base примерно на порядок меньше, наш matching latency на два-три порядка ниже, и мы предоставляем криптографическое доказательство того, какой именно код запущен, — что-то, что ни одна consensus-based система не может предоставить. Arch shipping первыми — позитивный сигнал для нашего thesis'а, потому что это валидирует категорию, и мы продаём premium продукт внутри категории, которую они создали.*

Этот параграф — самый короткий честный ответ на вопрос. Всё остальное в этом документе — supporting evidence.

---

## Приложение A — Проконсультированные источники

- [Arch Book — Introduction](https://docs.arch.network/book/introduction.html)
- [Arch Documentation — Overview](https://docs.arch.network/learn/overview)
- [Arch Book — Network Architecture](https://docs.arch.network/book/concepts/network-architecture.html)
- [Arch: Bitcoin's Execution Play — blocmates](https://www.blocmates.com/articles/arch-bitcoin-s-execution-play)
- [Arch Network Code Review — Token Metrics Research](https://research.tokenmetrics.com/p/arch-network)
- [Arch Documentation FAQ — GitBook](https://arch-network.gitbook.io/arch-documentation/developers/faq)
- [Arch Whitepaper — The Permissionless Financial Rails for a Bitcoin-denominated World](https://docs.arch.network/whitepaper.pdf)
- [What Is Arch Network? — MEXC Blog](https://blog.mexc.com/what-is-arch-network-reshape-bitcoins-native-defi/)
- [Bitcoin Programmability: The Complete Picture — Arch Network Blog](https://www.blog.arch.network/bitcoin-programmability-the-complete-picture/)

## Приложение B — Кросс-ссылки внутри нашей собственной документации

- `btc-perp-dex-feasibility.md` — полный BTC-portability аргумент для нашей архитектуры. Этот сравнительный документ — competitive слой; тот — технический слой.
- `sgx-enclave-capabilities-and-limits.md` — trust модель, на которой мы покоимся, включая честные пределы SGX. Arch не покоится на этой модели вообще; сравнение trust-предположений требует понимания обеих.
- `deployment-procedure.md` — operator ceremony, определяющая наш identity-based trust set. Это документ, который регулятор или институциональный контрагент захочет увидеть.
- `xls-survey-for-perp-dex.md` — почему мы выбрали XRPL первыми, а не BTC первыми. Аргументация там (нативная программируемость, быстрая finality, нативный стейблкоин) предшествует появлению Arch и всё ещё держится.
- `feedback_bilingual_docs.md` — bilingual policy. Этот документ имеет русскую версию.
