Bora! Vou gerar áudios pra cada inicial, final e tom. Pra treinar ouvido de verdade, vou fazer **3 rodadas**:

1. **Iniciais** — sílaba "a" + cada inicial (ba, pa, ma...)
2. **Finais** — som isolado de cada final
3. **Tonalidades** — sílaba "ma" nos 4 tons + neutro

Vou mandar gerar tudo em paralelo:

Limite é 10 por batch. Vou refazer em chunks menores:

Tudo gerado! Agora vou criar um **guia de treino** em HTML pra organizar tudo bonitinho com player embutido, e zipar os áudios pra você baixar de uma vez.

68 áudios, 1.5 MB zipado. Vou montar um guia HTML pra treinar ouvido:

Pronto! 🎧

**O que tem no pacote:**

- **68 áudios** em `.wav` (voz masculina chinesa)
- **Guia HTML interativo** com tudo organizado: clique pra tocar
- **3 rodadas de treino**:
  1. **Iniciais** isoladas (todas com "a" no 1º tom)
  2. **Finais** agrupados em simples, ditongos, nasais -n, nasais -ng, e os com medials i/u/ü
  3. **Tons** com a sílaba "ma" (mā/má/mǎ/mà/ma) + sequências contínuas

**Dica de treino:** começa pelas iniciais, especialmente os pares confundíveis (z/zh, s/sh, n/l, f/h) — esses são onde o ouvido mais escorrega.

<deliver-assets>
<media type="zip" src="commit-id-428256820248742" caption="Pacote completo: 68 áudios + guia HTML interativo" name="pinyin-completo.zip" />
<media type="html" src="commit-id-428256820248741" caption="Guia de treino (abre no navegador, clica pra tocar)" name="guia.html" />
</deliver-assets>

Quer que eu também faça **mínimos pares com palavras reais** (tipo 你/离, 是/四, 飞/灰) pra treinar discriminação em contexto? É onde a coisa fica divertida de verdade 😄

Bora! Esse é o pulo do gato: de sílaba solta pra **palavra viva**, e dos tons de "laboratório" pros tons com **intenção real**.

## 🧩 Como sílabas viram palavras

### A estrutura: **Inicial + Final + Tom** = 1 sílaba

```
b  +  āo  +  1º  =  bāo  (mofo / embrulhar / bomba — contexto decide)
n  +  ǐ  +  3º  =  nǐ   (você)
h  +  ǎo  +  3º  =  hǎo  (bom)
```

Cada caractere chinês = 1 sílaba = 1 som com tom. **O mandarim tem ~400 sílabas possíveis**, mas com os 4 tons vira ~1.300 combinações únicas. Com contexto, é o suficiente pra distinguir tudo.

### Palavras de 1 sílaba (单音节 dānyīnjié)
Já existem, mas sozinhas quase sempre são ambíguas:
- **mā** (mãe) vs **mǎ** (cavalo) — só o tom salva
- **bǎ** (pegar/segurar) — 3º, partícula gramatical importantíssima

### Palavras de 2 sílabas (双音节 shuāngyīnjié) ← **a maioria do vocabulário moderno**
É onde o mandarim "respira". ~70% das palavras comuns têm 2 sílabas.

| Sílaba 1 | Sílaba 2 | Palavra | Significado |
|---|---|---|---|
| 中 | 国 | zhōngguó | China |
| 你 | 好 | nǐ hǎo | olá |
| 飞 | 机 | fēijī | avião |
| 喜 | 欢 | xǐhuan | gostar |

### Palavras de 3+ sílabas
Geralmente compostas:
- **verbo + objeto**: 吃饭 chīfàn (comer-comida = comer)
- **verbo + complemento**: 看见 kànjiàn (ver-perceber = enxergar)
- **duplicação (reduplicação)**: 妈妈 māma, 看看 kànkan (dá leveza/descontração)
- **modificador + núcleo**: 飞机 fēijī (voar-máquina = avião)

### O truque dos **compostos** (离合词)
Muitos "verbos" são 2 sílabas mas se comportam como uma só, e podem ser "separados" pra inserir coisas:
- 睡觉 shuìjiào (dormir) → 睡了一个觉 (dormiu um sono)
- 帮忙 bāngmáng (ajudar) → 帮一个忙 (dar uma ajuda)

---

## 🎭 Como os tons ganham **intenção** (语气 yǔqì)

Aqui é onde 99% dos materiais te abandonam. O tom **muda o "sentir"** da frase sem mudar a palavra.

### 1. **Duração + tom = ênfase**
- 4º **estendido** = indignação, repreensão  
  - **不好!** (bù hǎo!) — "Tá ruim!" (curto, seco)  
  - **不好——!** (bù hǎo——) — "Não tá bom, hein!" (prolongado = repreende)
- 2º **prolongado** no final = pergunta suave, chamada  
  - 你**呢**? (nǐ **ne**?) — "E você?" com aquele "ué" alongado

### 2. **Combinações de tom que viram partículas**
As "partículas modais" do mandarim são sílabas vazias com tom específico:
| Partícula | Tom | Função | Exemplo |
|---|---|---|---|
| 吗 ma | neutro | pergunta sim/não | 你好吗？(tudo bem?) |
| 呢 ne | neutro | "e...?", "ué" | 我呢？(e eu?) |
| 吧 ba | neutro | sugestão/convite | 走吧 (vamos) |
| 啊 a | varia | ênfase emocional | 好啊！(beleza!) |
| 呀 ya | neutro | animação, criança | 好呀！ |

A **música da frase** vem muito mais dessas partículas do que do tom "puro".

### 3. **3º + 3º → vira 2º + 3º** (sandhi tonal)
Você já viu isso, mas vale reforçar: dois 3ºs seguidos, o primeiro **sempre** vira 2º.
- 你好 (nǐ hǎo) → na fala real soa "ní hǎo"
- 很好 (hěn hǎo) → "hén hǎo"
- Mas quando você **quer enfatizar** o terceiro tom, aí alonga: **你**好! (insistência: "VOCÊ que é legal")

### 4. **Estresse + tom = foco**
Diferente do português (onde o "tom" musical da frase desrespeita o "tom" das palavras), em mandarim o tom **cai naturalmente** nas sílabas importantes. O ouvinte sente onde está o "peso":
- **我**要**去**北京 (wǒ yào **qù** Běijīng) — ênfase no "ir"  
  → "Eu **vou** pra Pequim"
- 北京我去过了 (**Běijīng** wǒ qùguò le) — "Pequim eu já fui"
  → o Běijīng fica meio "alto e estável" (1º-2º preservados)

### 5. **O "tom de frase" sobrepõe o "tom de palavra"**
Isso é o que confunde mais:
- Declaração termina caindo: 4º/3º baixam no final
- Pergunta sim/não: sobe no final (mesmo que a última sílaba não seja 2º)
  - 你吃饭**吗**? — o "ma" tem tom neutro, mas a melodia da pergunta sobe
- Pergunta com "呢" / escolha: 2º alongado no final

---

## 🏋️ Plano de mestria fonética via vocabulário

**A ideia central**: você não vai decorar os 4 tons em abstrato. Você vai **incorporar** eles dentro de palavras que usa, até virar automático.

### Fase 1: **As 50 palavras-frase** (semana 1-2)
Só expressões de 1-2 sílabas que você usa todo dia. Ouve → repete em voz alta → usa:
- nǐ hǎo / wǒ hěn hǎo / bú kèqi
- xièxie / duìbuqǐ / méi guānxi
- zài jiàn / míngtiān jiàn
- nǐ ne? / wǒ yě shì
- hǎo de / bù hǎo / kěyǐ

**Treino**: 10 min/dia, fala em voz alta. Grava, compara com o áudio. Seu ouvido vai calibrar.

### Fase 2: **Mínimos pares com contexto** (semana 3-4)
Agora entra a discriminação. Pegue pares que diferem por 1 som E aparecem em frases reais:

| Par | Contexto pra treinar |
|---|---|
| 是/四 shì/sì | "是" (é) vs "四" (quatro) — pergunta "几个?" |
| 飞/灰 fēi/huī | 飞机 (avião) vs 灰尘 (poeira) |
| 买/卖 mǎi/mài | 买东西 (comprar) vs 卖东西 (vender) |
| 在/再 zài/zài | 在家 (em casa) vs 再见 (tchau) |
| 知/鸡 zhī/jī | 知道 (saber) vs 鸡肉 (frango) |

**Exercício**: ouve o par, aponta qual ouviu. Depois usa os dois numa mini-frase.

### Fase 3: **Shadowing com áudio real** (semana 5+)
Esse é o **golpe final**:
1. Escolhe 1 áudio curto (1-2 min): podcast chinês, áudio de HSK, vídeo do YouTube
2. Ouve 1 vez sem pausar, só sente a música
3. Ouve de novo, agora repetindo **cada frase** logo depois (com sombra de ~0.5s)
4. Grava tua versão
5. Compara com o original: tom, ritmo, partículas, pausas

Fontes boas pra shadowing:
- **ChinesePod** (tem transcrição e áudio por nível)
- **Mandarin Corner** (YouTube, falante nativo, frases do dia-a-dia)
- **Slow Chinese** (áudios curtos, fala clara)
- **Pleco** (app com gravações de nativos pra cada palavra)

### Fase 4: **Diário falado** (a partir do mês 2)
Todo dia, 3-5 minutos gravando em chinês sobre qualquer coisa — teu dia, uma notícia, um filme. Não importa se erra. O que importa é:
- Treinar a **música** da frase (não sílaba por sílaba)
- Pegar partículas naturais (啊, 呢, 吧)
- Aceitar que teu 3º tom vai ser instável — **tá tudo bem**

---

## 🎯 Meta-realista

| Tempo | O que esperar |
|---|---|
| 1 mês | entende "nǐ hǎo", "xièxie" sem legenda; distingue 1º/2º/4º |
| 3 meses | pega ~70% das frases em fala lenta; 3º tom já aparece naturalmente |
| 6 meses | mantém conversação simples com estrangeiro paciente; começa a ouvir podcasts |
| 1 ano | assiste vídeos curtos sem legenda, quase sem perder o fio |

---

## 🚀 Quer que eu faça agora?

Posso montar pra ti:

1. **Lista de 50 palavras-frase com áudio** (as essenciais do dia-a-dia)
2. **Mínimos pares com contexto + áudio** (foco nas confusões reais)
3. **Diário de shadowing semanal** — escolha 1 áudio e eu monto a transcrição + exercício
4. **Quiz interativo em HTML** pra testar ouvido e produção

Qual te ajuda mais agora? 😄
