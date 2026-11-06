/* Svit Editor — англійська мова інтерфейсу.
   Перекладає текст сторінки на льоту: точні збіги → словник, складені рядки → фрагменти й шаблони.
   Тексти, які пише Claude (назви роликів, коментарі), позначені класом .noi і не чіпаються. */
(function () {
  const EN = {
    // шапка
    "AI-монтаж · Claude × DaVinci": "AI editing · Claude × DaVinci",
    "Пишеш словами —": "You write words —",
    "воно ріже": "it cuts",
    "Зум, ритм, субтитри, кошторис.": "Zoom, rhythm, subtitles, cost estimate.",
    "★ МОНТАЖ ★": "★ EDIT ★",
    // ключ
    "Вітаю в Svit Editor": "Welcome to Svit Editor",
    "Щоб монтувати, програмі потрібен ключ Claude — це як пароль. Вставляється один раз.": "To edit, the app needs a Claude key — it's like a password. You paste it once.",
    "Створи ключ на сайті Claude": "Create a key on the Claude website",
    "Увійди → Create Key → скопіюй": "Log in → Create Key → copy",
    "Відкрити сайт": "Open website",
    "Встав ключ сюди": "Paste the key here",
    "Перевірити і зберегти": "Check and save",
    "Перевіряю…": "Checking…",
    "Кількох доларів вистачить надовго": "A few dollars will last a long time",
    "Ключ має починатися з sk-ant-": "The key must start with sk-ant-",
    "✓ Ключ працює": "✓ Key works",
    "Не вдалося перевірити ключ": "Couldn't check the key",
    // блок 1
    "Що змонтувати": "What to edit",
    "Головне поле. Опиши своїми словами, що хочеш отримати: скільки відео, про що, які моменти брати, де робити зум, як кадрувати. Чим конкретніше — тим краще.": "The main field. Describe in your own words what you want: how many videos, what about, which moments to take, where to zoom, how to frame. The more specific, the better.",
    "Наприклад: з усіх записів концертів зроби 5 вертикальних відео по 20–30 секунд. Бери дропи й моменти, де зал співає. На ударних — різкий зум, тримай мене в центрі кадру.": "For example: from all the concert recordings make 5 vertical videos of 20–30 seconds. Take the drops and moments where the crowd sings. On the hits — a sharp zoom, keep me in the centre of the frame.",
    "Напиши, що змонтувати, або вибери приклад": "Write what to edit, or pick an example",
    "Концерт → кліпи": "Concert → clips",
    "Інтерв'ю → цитати": "Interview → quotes",
    "Бекстейдж → смішне": "Backstage → funny",
    "Тизер треку": "Track teaser",
    "З усіх записів концертів зроби 5 вертикальних відео по 20–30 секунд. Бери найенергійніші моменти: дропи, де зал співає, кульмінації. Початок кожного — одразу на піку. На ударних моментах роби різкий зум 1.3–1.5, тримай мене в центрі кадру.": "From all the concert recordings make 5 vertical videos of 20–30 seconds. Take the most energetic moments: drops, where the crowd sings, climaxes. Start each one right at the peak. On the hits do a sharp 1.3–1.5 zoom, keep me in the centre of the frame.",
    "Знайди 4 найсильніші думки з інтерв'ю, кожна 30–45 секунд, з цікавим хуком на початку. Виріжи паузи й слова-паразити. На ключовій фразі легкий зум 1.15.": "Find the 4 strongest ideas from the interview, 30–45 seconds each, with an interesting hook at the start. Cut pauses and filler words. A gentle 1.15 zoom on the key phrase.",
    "Збери 3 короткі смішні моменти з бекстейджу, до 20 секунд кожен, з панчлайном у кінці.": "Collect 3 short funny backstage moments, up to 20 seconds each, with a punchline at the end.",
    "Зроби одне відео на 15 секунд: тизер треку. Найемоційніша частина приспіву, склейки в ритм, наприкінці зум на обличчя.": "Make one 15-second video: a track teaser. The most emotional part of the chorus, cuts on the rhythm, a zoom on the face at the end.",
    "Референси — чим надихатись": "References — what inspires you",
    "Відео й кадри, які тобі подобаються. Svit Editor порахує їхній темп склейок і покаже Claude кадри з різних планів — монтаж вийде в схожому дусі. Посилання завантажуються в мінімальній якості лише для аналізу і видаляються.": "Videos and frames you like. Svit Editor measures their cutting pace and shows Claude frames from different shots — the edit comes out in a similar spirit. Links are downloaded in minimal quality only for analysis and then deleted.",
    "Встав посилання: TikTok · Reels · Shorts · YouTube": "Paste a link: TikTok · Reels · Shorts · YouTube",
    "Додати": "Add",
    "Додаю…": "Adding…",
    "Перетягни сюди відео чи скріни, які подобаються": "Drop videos or screenshots you like here",
    "Відео": "Videos",
    "Скріни": "Screens",
    "Референс додано": "Reference added",
    // блок 2
    "Матеріал": "Footage",
    "Звідки брати відео в DaVinci. Можна виділити багато кліпів одразу або взяти всю папку Media Pool — наприклад, усі записи концертів.": "Where to take videos from in DaVinci. You can select many clips at once or take a whole Media Pool folder — for example, all concert recordings.",
    "Виділені": "Selected",
    "Папка Media Pool": "Media Pool folder",
    "З таймлайну": "From timeline",
    "Перетягнуті": "Dropped",
    "Очистити": "Clear",
    "Оновити": "Refresh",
    "↻ Оновити": "↻ Refresh",
    "Нічого не вибрано": "Nothing selected",
    "Виділи кліпи в DaVinci": "Select clips in DaVinci",
    "Виділи кліпи в Media Pool і натисни «Оновити»": "Select clips in the Media Pool and press “Refresh”",
    "Відкрий потрібну папку в Media Pool і натисни «Оновити»": "Open the folder you need in the Media Pool and press “Refresh”",
    "Відкрий таймлайн з кліпами і натисни «Оновити»": "Open a timeline with clips and press “Refresh”",
    "Перетягни кліпи з DaVinci або Finder прямо в це вікно": "Drag clips from DaVinci or Finder straight into this window",
    "Спершу вибери матеріал і натисни «Оновити»": "First choose the footage and press “Refresh”",
    "Не вдалося додати кліпи": "Couldn't add the clips",
    "Не вдалося оновити": "Couldn't refresh",
    "Кидай сюди": "Drop here",
    "Кліпи з DaVinci · файли з Finder · папку · трек для музики": "Clips from DaVinci · files from Finder · a folder · a music track",
    "Svit Editor відкритий не з DaVinci. Запускай його через DaVinci: Workspace → Scripts → Svit Editor.": "Svit Editor wasn't opened from DaVinci. Launch it via DaVinci: Workspace → Scripts → Svit Editor.",
    "Відкрий Svit Editor через DaVinci: Workspace → Scripts": "Open Svit Editor via DaVinci: Workspace → Scripts",
    // блок 3
    "Музика": "Music",
    "Додай трек — Svit Editor знайде темп і удари, а Claude поріже відео під біт. Трек ляже на аудіодоріжку, звук камер вимкнеться.": "Add a track — Svit Editor finds the tempo and beats, and Claude cuts the video to the beat. The track goes on the audio track and camera sound is muted.",
    "Монтаж під аудіо": "Edit to audio",
    "Склейки на біт, трек на аудіодоріжці": "Cuts on the beat, track on the audio track",
    "Перетягни аудіофайл у вікно або": "Drop an audio file into the window or",
    "Вибрати трек": "Choose a track",
    "Прослухати": "Listen",
    "Стоп": "Stop",
    "Інший трек": "Another track",
    "тягни ручки — вибери шматок пісні": "drag the handles — pick a part of the song",
    "Трек додано: вибери шматок пісні": "Track added: pick a part of the song",
    "Не вдалося відтворити": "Couldn't play",
    // розширені
    "Розширені налаштування": "Advanced settings",
    "Кадр": "Frame", "Динаміка": "Pace", "Зуми": "Zoom", "Ефекти": "Effects", "Колір": "Color",
    "Результат": "Output", "Аналіз": "Analysis",
    "Співвідношення сторін": "Aspect ratio",
    "Розмір готових відео. Якщо джерело іншої форми, кадр сам наблизиться й обріжеться, а Claude вибере, яку частину показати.": "Size of the finished videos. If the source has a different shape, the frame zooms and crops itself, and Claude picks which part to show.",
    "Як є": "As is", "Вертикальне": "Vertical", "Квадрат": "Square", "Класичне": "Classic", "Горизонтальне": "Horizontal",
    "Частота кадрів (FPS)": "Frame rate (FPS)",
    "Скільки кадрів за секунду матиме таймлайн і готове відео. 24 — кіно, 25 — стандарт для Європи, 30 — соцмережі, 60 — дуже плавно. «Як у джерела» — без змін.": "How many frames per second the timeline and finished video will have. 24 — cinema, 25 — European standard, 30 — social media, 60 — very smooth. “Same as source” — unchanged.",
    "Як у джерела": "Same as source", "як у джерела": "same as source", "FPS як у джерела": "FPS same as source",
    "Темп нарізки": "Cutting pace",
    "Як часто будуть склейки. Швидка — короткі шматки для TikTok і Reels. Повільна — довгі плани з природними паузами, як у влогах на YouTube.": "How often the cuts happen. Fast — short pieces for TikTok and Reels. Slow — long shots with natural pauses, like YouTube vlogs.",
    "Швидка": "Fast", "Нормальна": "Normal", "Повільна": "Slow",
    "TikTok, Reels. Склейки кожні 1–2 с, без пауз": "TikTok, Reels. Cuts every 1–2 s, no pauses",
    "Баланс. Шматки 3–6 с, ритм тримається": "Balanced. 3–6 s pieces, the rhythm holds",
    "YouTube, влог. Довгі плани, природні паузи": "YouTube, vlog. Long shots, natural pauses",
    "Абстрактність ідей": "Abstraction of ideas",
    "Наскільки сміливо Claude вигадує. Ліворуч — класичний зрозумілий монтаж за правилами. Посередині — асоціативні склейки, візуальні рими, нелінійність. Праворуч — артхаус: монтаж як сон чи знайдена плівка, lost wave, dreamcore, свідоме ламання правил.": "How boldly Claude invents. Left — classic, clear editing by the rules. Middle — associative cuts, visual rhymes, non-linearity. Right — art-house: editing like a dream or found footage, lost wave, dreamcore, deliberately breaking the rules.",
    "класика": "classic", "творчо": "creative", "артхаус": "art-house",
    "Класика: чиста історія, суворі правила монтажу": "Classic: a clean story, strict editing rules",
    "Основа класична + 1–2 знахідки: match cut, контраст тиші й вибуху": "Classic base + 1–2 tricks: match cut, silence-to-explosion contrast",
    "Асоціативно: візуальні рими, нелінійність, сміливий ритм": "Associative: visual rhymes, non-linearity, bold rhythm",
    "Експеримент: кліпове мислення, свідомі jump cut'и, контрасти": "Experimental: music-video thinking, deliberate jump cuts, contrasts",
    "Артхаус: монтаж як сон чи знайдена плівка — lost wave, dreamcore": "Art-house: editing like a dream or found footage — lost wave, dreamcore",
    "Скільки відео зробити": "How many videos",
    "Скільки окремих готових роликів зробити з усього матеріалу. «Авто» — Claude візьме кількість з твого запиту.": "How many separate finished videos to make from all the footage. “Auto” — Claude takes the number from your request.",
    "Довжина кожного відео": "Length of each video",
    "Скільки триватиме КОЖЕН готовий ролик (а не відео-джерело). «Авто» — за запитом.": "How long EACH finished video lasts (not the source video). “Auto” — from the request.",
    "Авто": "Auto", "Авто — як у запиті": "Auto — as in the request",
    "До 15 секунд": "Up to 15 seconds", "до 15 секунд": "up to 15 seconds",
    "15–30 секунд": "15–30 seconds", "30–60 секунд": "30–60 seconds", "1–3 хвилини": "1–3 minutes", "3–10 хвилин": "3–10 minutes",
    "Розміщення": "Layout",
    "«Один таймлайн» — усі ролики підряд, кожен позначений маркером. «Окремі» — кожен ролик на своєму таймлайні.": "“One timeline” — all videos in a row, each marked with a marker. “Separate” — each video on its own timeline.",
    "Усе на одному таймлайні": "All on one timeline", "Кожне відео окремо": "Each video separately",
    "Субтитри": "Subtitles", "Слова на окремій доріжці, стиль — в Inspector": "Words on a separate track, style in the Inspector",
    "Потрібне «Слухати слова» на вкладці «Аналіз».": "Needs “Listen to words” on the “Analysis” tab.",
    "Одразу експортувати MP4": "Export MP4 right away",
    "Після монтажу DaVinci сам експортує кожен ролик окремим MP4.": "After editing DaVinci exports each video as a separate MP4.",
    "У папку Фільми → Svit Editor": "To the Movies → Svit Editor folder",
    "Кадрування": "Framing",
    "Статично наближує і зсуває кадр, щоб головне було в центрі": "Statically zooms and shifts the frame so the main thing is centred",
    "Наприклад, горизонтальне відео у вертикальному форматі: Claude вибере, яку частину кадру показати і наскільки наблизити. Це не ефект — просто правильний кадр.": "For example, a horizontal video in a vertical format: Claude picks which part of the frame to show and how far to zoom. It's not an effect — just the right framing.",
    "Динамічний зум": "Dynamic zoom",
    "Легкий плавний рух — наїзди й від'їзди, щоб картинка жила": "Light smooth motion — push-ins and pull-outs so the picture feels alive",
    "На кожному шматку кадр повільно наближається або віддаляється на кілька відсотків. Робиться через Fusion, тож експорт трохи довший.": "On each piece the frame slowly zooms in or out by a few percent. Done in Fusion, so export takes a bit longer.",
    "Сила руху": "Motion strength",
    // ефекти
    "бета": "beta",
    "Claude ставить їх сам — під біт, референси й настрій": "Claude places them itself — to the beat, references and mood",
    "Ефекти робляться через Fusion у DaVinci, тож експорт трохи довший. Познач, які дозволено — Claude використає їх лише там, де вони підсилюють момент.": "Effects are made in Fusion in DaVinci, so export takes a bit longer. Mark which are allowed — Claude will use them only where they strengthen the moment.",
    "Тряска": "Shake", "на ударах і дропах": "on hits and drops",
    "Спалах": "Flash", "різке світло на сильній долі": "sharp light on the downbeat",
    "З темряви": "From dark", "проявлення: початок, нова частина": "fade-in: start, new section",
    "З розмиття": "From blur", "мрійливий вхід у кадр": "dreamy entrance into the shot",
    "RGB-глітч": "RGB glitch", "розшарування кольорів на склейці": "colour split on the cut",
    "Світіння": "Glow", "сцена, світло, прожектори": "stage, lights, spotlights",
    "Чорно-біле": "Black & white", "драма, ностальгія": "drama, nostalgia",
    "Зерно": "Grain", "плівкова фактура": "film texture",
    "Сила ефектів": "Effect strength",
    "делікатно": "subtle", "помітно": "noticeable", "на повну": "full on",
    "Повільний зум": "Slow zoom",
    "Плавний наїзд / від'їзд": "Smooth push-in / pull-out",
    "Автоматизація зуму на кожному шматку (ключові кадри у Fusion)": "Zoom automation on every piece (keyframes in Fusion)",
    "Сила зуму": "Zoom strength", "ледь-ледь": "barely", "виразно": "pronounced",
    "На весь ролик": "Whole video",
    "Як Adjustment Clip поверх нарізки: ефект однаковий на всьому ролику. Накладається на кожен шматок у Fusion — правиться там же, у вузлах Blur і SoftGlow (halation).": "Like an Adjustment Clip over the edit: the effect is the same across the whole video. Applied to each piece in Fusion — edit it there, in the Blur and SoftGlow (halation) nodes.",
    "Дрімі-розмиття": "Dreamy blur",
    "М'яке сяйво як уві сні: розмита копія світиться поверх різкого кадру": "A soft dreamlike glow: a blurred copy shines over the sharp frame",
    "Сила розмиття": "Blur strength", "ледь": "slight", "м'яко": "soft", "сильно": "strong",
    "Halation": "Halation",
    "Червоно-помаранчеве світіння навколо світла, як на плівці": "Red-orange glow around lights, like on film",
    "Сила halation": "Halation strength", "натяк": "hint", "горить": "burning",
    "Переходи": "Transitions",
    "Переходи між шматками через Fusion: кінець одного плану і початок наступного анімуються разом. Більшість склейок лишаються прямими — Claude ставить переходи на сильні долі, зміни частин і настрою.": "Transitions between pieces via Fusion: the end of one shot and the start of the next animate together. Most cuts stay straight — Claude places transitions on downbeats, section and mood changes.",
    "Переходи між планами": "Transitions between shots",
    "Claude ставить їх сам, приблизно на кожну 3–5-ту склейку": "Claude places them itself, roughly on every 3rd–5th cut",
    "Швидкість переходів і спалаху": "Transition and flash speed",
    "повільно": "slow", "середньо": "medium", "блискавично": "lightning fast",
    "Наїзд": "Zoom", "різкий зум з розмиттям, на біт": "sharp zoom with blur, on the beat",
    "Свайп": "Swipe", "змах кадру вбік": "the frame whips sideways",
    "Через чорне": "Through black", "зміна частини, драма": "section change, drama",
    "Через біле": "Through white", "кульмінація, дроп": "climax, drop",
    "Глітч": "Glitch", "кольори смикаються": "colours twitch",
    "Розмиття": "Blur", "м'яко, як спогад": "soft, like a memory",
    "Вінтаж / плівка": "Vintage / film",
    "Фактура на весь ролик: касета, плівка, старий телевізор. Робиться у Fusion на кожному шматку — експорт довший. Claude монтує в дусі обраної фактури.": "A texture for the whole video: tape, film, an old TV. Made in Fusion on each piece — export takes longer. Claude edits in the spirit of the chosen texture.",
    "Без вінтажу": "No vintage", "чиста картинка": "clean picture",
    "Claude обере за запитом": "Claude picks from the request",
    "Касета VHS": "VHS tape", "шум, трекінг, кольори з'їжджають": "noise, tracking, colours drift",
    "Камкордер 90-х": "90s camcorder", "Hi8, тепло, аматорськи": "Hi8, warm, amateur",
    "Плівка 8 мм": "8 mm film", "хроніка: зерно, мерехтіння": "home movie: grain, flicker",
    "Плівка 16 мм": "16 mm film", "інді-кіно, м'яко": "indie film, soft",
    "Телевізор": "Old TV", "рядки, віньєтка, світіння": "scan lines, vignette, glow",
    "Lost wave": "Lost wave", "вицвіле, «знайдена плівка»": "faded, “found footage”",
    "Ч/Б кіно": "B&W cinema", "контраст, мерехтіння": "contrast, flicker",
    "Vaporwave": "Vaporwave", "рожеве світіння, мрія": "pink glow, dream",
    "Сила вінтажу": "Vintage strength", "убита плівка": "wrecked film",
    // cinematic
    "Режим для кліпів, лірик-відео і короткого кіно. Claude монтує не як швидку нарізку для TikTok, а як кліп: довші плани, що дихають, повільні плавні наїзди, склейки на фразах і рядках пісні, крупні плани на приспів, деталі між куплетами. Якщо ти зняв кілька дублів під трек — увімкни музику, і Svit сам вирівняє дублі з піснею, щоб губи збігались.": "A mode for music videos, lyric videos and short films. Claude edits not like a fast TikTok cut but like a music video: longer shots that breathe, slow smooth push-ins, cuts on phrases and lyric lines, close-ups on the chorus, details between verses. If you shot several takes to a track, turn on music and Svit aligns the takes with the song so the lips match.",
    "Монтаж як у кліпах і кіно, а не як швидка нарізка": "Editing like music videos and films, not a fast cut",
    "Для кліпу, лірик-відео, короткого фільму. Довші плани, повільні наїзди, склейки на фразах пісні, крупні плани на приспів.": "For a music video, lyric video, short film. Longer shots, slow push-ins, cuts on song phrases, close-ups on the chorus.",
    "Кінематографічність": "Cinematic level", "легко": "light", "кліп": "music video", "кіно": "cinema",
    "Синхрон дублів (lip-sync)": "Take sync (lip-sync)",
    "Кілька дублів під трек — Svit знайде, де в пісні кожен, і різатиме між ними в синхроні. Потрібна музика в блоці 3": "Several takes to a track — Svit finds where in the song each one is and cuts between them in sync. Needs music in block 3",
    "Синхронізую дублі з піснею": "Syncing takes with the song",
        // колір
    "Автоконтраст і експозиція": "Auto contrast and exposure",
    "Svit дивиться на кожне відео й сам підбирає контраст, чорне й гаму": "Svit looks at each video and picks contrast, blacks and gamma itself",
    "Пласке (лог) відео отримає більше контрасту, темне — трохи світліше, підняті чорні опустяться. Кожне джерело — окремо. Правиться у Fusion: вузол BrightnessContrast першим у ланцюжку.": "Flat (log) video gets more contrast, dark video a bit brighter, lifted blacks come down. Each source separately. Edit it in Fusion: the BrightnessContrast node first in the chain.",
    "Сила корекції": "Correction strength", "повністю": "fully",
    "Камера і лог": "Camera and log", "скоро": "soon",
    "Камера": "Camera", "Лог-профіль / гама": "Log profile / gamma",
    "напр. Sony A7 IV": "e.g. Sony A7 IV", "напр. S-Log3 / S-Gamut3.Cine": "e.g. S-Log3 / S-Gamut3.Cine",
    "Підібрати автоматично": "Match automatically",
    "У наступному оновленні: вкажеш камеру й лог, у якому знімав, і Svit правильно переведе в нормальний колір.": "In the next update: you'll set the camera and log you shot in, and Svit will convert it to normal colour correctly.",
    // аналіз
    "Слухати слова": "Listen to words",
    "Розпізнає слова й тексти пісень з таймкодами. Працює на твоєму Маці, безкоштовно.": "Recognises words and lyrics with timecodes. Runs on your Mac, for free.",
    "Для інтерв'ю, влогів і субтитрів. На довгих концертах займає час": "For interviews, vlogs and subtitles. Takes time on long concerts",
    "Мова відео": "Video language", "Автовизначення": "Auto-detect", "Українська": "Ukrainian",
    "Якість розпізнавання": "Recognition quality", "Швидко": "Fast", "Точно": "Accurate", "Максимально точно": "Most accurate",
    "Точніше — повільніше. Нова якість один раз докачається.": "More accurate is slower. A new quality level downloads once.",
    "Дивитись кадри": "Look at frames",
    "Claude подивиться маленькі кадри з відео: де сцена, де люди, що відбувається.": "Claude looks at small frames from the videos: where the stage is, where the people are, what's happening.",
    "Щоб правильно кадрувати й обирати красиві моменти": "To frame correctly and pick beautiful moments",
    "Модель Claude": "Claude model",
    "Sonnet — найкращий баланс. Opus — найрозумніший для складних запитів. Haiku — найдешевший для простих задач.": "Sonnet — the best balance. Opus — the smartest for complex requests. Haiku — the cheapest for simple tasks.",
    "Sonnet — швидко й вигідно": "Sonnet — fast and good value", "Opus — найрозумніший": "Opus — the smartest", "Haiku — найдешевший": "Haiku — the cheapest",
    "Увімкни «Слухати слова» або «Дивитись кадри»": "Turn on “Listen to words” or “Look at frames”",
    // кошторис
    "Кошторис · токени": "Estimate · tokens",
    "Скільки токенів приблизно забере цей монтаж: залежить від довжини матеріалу, кількості кадрів, скрінів і роликів. Точну суму програма порахує перед стартом і покаже в кінці.": "Roughly how many tokens this edit will take: it depends on the footage length, number of frames, screenshots and videos. The app counts the exact amount before starting and shows it at the end.",
    "Виділи матеріал, щоб побачити ціну": "Select footage to see the price",
    "Змонтувати": "Edit",
    "Виділи матеріал": "Select footage",
    // прогрес
    "Не закривай вікно": "Don't close the window",
    "Минуло": "Elapsed", "Залишилось": "Remaining", "Токени": "Tokens",
    "Вигляд": "Look", "без нового монтажу · 0 токенів": "no re-edit · 0 tokens", "Фактура": "Texture",
    "як у монтажі": "as edited", "без вінтажу": "no vintage", "Вінтаж": "Vintage", "Фантоми": "Ghosts",
    "Дрімі-розмиття": "Dreamy blur", "Зерно": "Grain", "Контраст": "Contrast", "Сила ефектів": "Effect strength",
    "Швидкість переходів": "Transition speed", "натяк": "hint", "убита плівка": "wrecked film", "без": "none",
    "подвійні": "double", "вимк.": "off", "горить": "glowing", "сон": "dream", "густе": "heavy", "як знято": "as shot",
    "автоконтраст": "auto contrast", "делікатно": "subtle", "на повну": "full", "повільно": "slow", "блискавично": "lightning",
    "Скинути": "Reset", "Застосувати": "Apply", "як зараз": "as now", "Оновлюю вигляд…": "Updating look…",
    "Вигляд оновлено в DaVinci": "Look updated in DaVinci", "Зачекай, поки завершиться попередня дія": "Wait for the previous action to finish",
    "Рухай повзунки і натисни «Застосувати» — Svit оновить ефекти прямо на готових таймлайнах у DaVinci. Монтаж і склейки не змінюються, Claude не викликається, токени не витрачаються.": "Move the sliders and press Apply — Svit updates the effects right on the finished DaVinci timelines. Cuts stay the same, Claude is not called, no tokens are spent.",
    "наживо · 0 токенів": "live · 0 tokens", "Прибрати ефекти": "Remove effects", "Мій таймлайн": "My timeline",
    "Ефекти на мій таймлайн": "Effects on my timeline", "Закрити": "Close", "Шукаю відкритий таймлайн…": "Looking for the open timeline…",
    "У DaVinci не відкритий жоден таймлайн": "No timeline is open in DaVinci", "DaVinci не відповідає": "DaVinci is not responding",
    "Підкручую…": "Tuning…", "Перебудовую ефекти…": "Rebuilding effects…", "Прибираю ефекти…": "Removing effects…",
    "Зачекай, поки завершиться монтаж": "Wait for the edit to finish",
    "Накласти halation, дрімі, вінтаж, зерно на таймлайн, який ти змонтував сам. Без Claude, 0 токенів.": "Add halation, dreamy blur, vintage and grain to a timeline you edited yourself. No Claude, 0 tokens.",
    "Рухай повзунки — Svit одразу оновлює ефекти прямо на таймлайні в DaVinci, спершу шматок під курсором. Halation, дрімі, зерно, фантоми й контраст підкручуються миттєво; фактура, сила вінтажу, ефектів і переходів — перебудовуються. Монтаж не змінюється, Claude не викликається.": "Move the sliders — Svit updates the effects right on the DaVinci timeline, the clip under the playhead first. Halation, dreamy blur, grain, ghosts and contrast are tuned instantly; texture, vintage, effect and transition strength are rebuilt. Cuts stay the same, Claude is not called.",
    "Текст": "Text", "Слова пісні": "Song lyrics", "Субтитри з мови": "Speech subtitles",
    "Встав сюди текст пісні — кожен рядок стане субтитром.\n\n[Куплет 1]\nПерший рядок пісні\nДругий рядок пісні": "Paste the song lyrics here — each line becomes a subtitle.\n\n[Verse 1]\nFirst line of the song\nSecond line of the song",
    "У відео грає цей трек": "This track plays in the videos", "Знято під пісню з колонки — Svit підгонить відео під імпортований трек, щоб губи й рухи збігались": "Shot to the song from a speaker — Svit lines the videos up with the imported track so lips and moves match",
    "ВЕЛИКИМИ ЛІТЕРАМИ": "ALL CAPS", "Інакше — як написано в тексті": "Otherwise — as written",
    "Розпізнана мова з відео (інтерв'ю, влоги) на окремій доріжці, стиль — в Inspector": "Recognised speech from the videos (interviews, vlogs) on a separate track, style in the Inspector",
    "Встав текст пісні — по рядку на субтитр. Svit послухає трек з «Монтаж під аудіо», знайде, коли звучить кожен рядок, і покладе субтитри на окрему доріжку саме в такт співу. Порожні рядки й позначки [Приспів] пропускаються. Розпізнавання працює на твоєму Маці, безкоштовно.": "Paste the lyrics — one line per subtitle. Svit listens to the track from “Edit to audio”, finds when each line is sung and puts the subtitles on a separate track in time with the vocals. Empty lines and tags like [Chorus] are skipped. Recognition runs on your Mac, free.",
    "Svit порівнює звук кожного відео з треком і знаходить, яке місце пісні в ньому звучить. Тоді шматки відео стають на таймлайн рівно під той момент пісні.": "Svit compares each video's sound with the track and finds which part of the song plays in it, then places the clips exactly at that moment of the song.",
    "Пробіл — грати / пауза · двічі пробіл — на початок шматка": "Space — play / pause · double space — back to the start",
    "Пауза": "Pause", "Грати далі": "Resume", "Оновитись": "Update", "Тестові версії": "Test versions",
    "Пропонувати й alpha-версії з новими функціями — можуть бути нестабільні": "Also offer alpha versions with new features — may be unstable",
    "Більше не показувати при запуску": "Don't show at startup", "Оновлення встановлено": "Update installed", "Добре": "OK",
    " · тестова": " · test",
    "Svit Editor · мій таймлайн": "Svit Editor · my timeline",
    "Тривалість кожного відео": "Length of each video", "Вручну": "Custom", "15 с": "15 s", "30 с": "30 s", "60 с": "60 s",
    "з музикою — довжина = вибраний шматок треку": "with music — length = selected part of the track",
    "Пробіл — грати / пауза · синю лінію можна тягати": "Space — play / pause · drag the blue line to scrub",
    "Стоп": "Stop", "Грати / пауза (пробіл)": "Play / pause (space)",
    "Вигляд тексту": "Text look", "Svit-текст: шрифт, колір, ефекти": "Svit text: font, colour, effects", "Субтитри DaVinci": "DaVinci subtitles",
    "Шрифт": "Font", "Імпортувати": "Import", "Стандартний (Arial Bold)": "Default (Arial Bold)", "Розмір": "Size", "дрібний": "small", "величезний": "huge",
    "Колір": "Colour", "Свій колір": "Custom colour", "Ефекти тексту": "Text effects", "Світіння": "Glow", "яскраве": "bright", "Тінь": "Shadow", "густа": "heavy",
    "Обведення": "Outline", "товсте": "thick", "Позиція": "Position", "Зверху": "Top", "По центру": "Centre", "Знизу": "Bottom",
    "· вертикальне відео": "· vertical video", "· горизонтальне відео": "· horizontal video", "· квадрат": "· square",
    "Анімація": "Animation", "Без": "None", "Поява": "Fade", "Підйом": "Rise", "Поп": "Pop", "З розмиття": "From blur",
    "Сила": "Strength", "ледь": "subtle", "помітно": "strong", "Плавність": "Smoothness", "різко": "sharp", "плавно": "smooth",
    "Програти анімацію": "Play animation", "Перегляд на кадрі з твого відео — без токенів": "Preview on a frame from your video — no tokens",
    "Вибери матеріал — перегляд буде на кадрі з твого відео": "Pick footage — the preview will use a frame from your video",
    "Шрифт додано": "Font added", "Твої шрифти": "Your fonts", "Шрифти Mac": "Mac fonts",
    "Розпізнана мова з відео (інтерв'ю, влоги) — тим самим стилем, що нижче": "Recognised speech from the videos (interviews, vlogs) — in the same style as below",
    "Svit-текст — Svit малює кожен рядок твоїм шрифтом, кольором, світінням і halation та кладе на окрему доріжку з анімацією. Субтитри DaVinci — звичайна доріжка субтитрів, стиль налаштовується в Inspector.": "Svit text — Svit draws each line in your font, colour, glow and halation and puts it on its own track with animation. DaVinci subtitles — a regular subtitle track, styled in the Inspector.",
    "Хочеш, щоб ефекти були одним шаром над усім відео? Перетягни в DaVinci": "Want the effects as one layer over the whole video? In DaVinci drag",
    "Реперський стиль": "Rapper style", "рівно": "neat", "хаос": "chaos", "Колір ключових слів": "Key word colour",
    "Текст оживає: слова різного розміру й нахилу, частину слів розбиває на букви різного розміру, ключові слова — більші й кольором акценту. Ключові слова Svit обирає сам, або познач їх у тексті пісні *зірочками*.": "The text comes alive: words of different sizes and angles, some words split into letters of different sizes, key words bigger and in the accent colour. Svit picks key words itself, or mark them in the lyrics with *asterisks*.",
    "Ліпсінк-відео": "Lip-sync videos", "Вибрати": "Choose", "Де ти співаєш у кадр?": "Where do you sing on camera?",
    "Познач відео, де ти співаєш у кадр — Svit поставить їх у синхрон з треком і чергуватиме з вайбовими кадрами": "Mark the videos where you sing on camera — Svit syncs them with the track and alternates them with vibe shots",
    "Познач ліпсінк-відео. Svit знайде в їхньому звуці трек і поставить шматки рівно в синхрон, а Claude чергуватиме їх з вайбовими кадрами.": "Mark the lip-sync videos. Svit finds the track in their sound and puts the clips exactly in sync, and Claude alternates them with vibe shots.",
    "Пошук за назвою": "Search by name", "Зняти всі": "Clear all", "Готово": "Done", "Спершу вибери матеріал у блоці 2": "Pick footage in block 2 first",
    "Svit Editor · ліпсінк": "Svit Editor · lip-sync",
    "У відео є ліпсінк": "The videos have lip-sync", "Ліпсінк-відео вручну": "Lip-sync videos manually",
    "Svit сам знайде відео, де ти співаєш під трек, поставить їх у синхрон і чергуватиме з вайбовими кадрами": "Svit finds the videos where you sing to the track, syncs them and alternates them with vibe shots",
    "Svit слухає звук кожного відео і шукає в ньому трек. Де знайшов — це ліпсінк: шматки стають рівно в синхрон з піснею. Якщо якесь відео не знайдеться — познач його вручну кнопкою нижче, для позначених Svit слухає уважніше.": "Svit listens to each video and looks for the track in it. Where it finds it, that's lip-sync: the clips go exactly in sync with the song. If a video isn't found, mark it manually below — Svit listens more closely to marked ones.",
    "Звичайна доріжка субтитрів: текст і час правиш прямо на таймлайні, стиль — в Inspector.": "A regular subtitle track: edit text and timing right on the timeline, style in the Inspector.",
    "Реперський стиль малюється картинками: рядки можна посувати й розтягувати на таймлайні, але слова не редагуються. Постав «Реперський стиль» на 0 — і текст буде редагованим.": "Rapper style is drawn as images: lines can be moved and stretched on the timeline, but the words can't be edited. Set Rapper style to 0 to get editable text.",
    "Кожен рядок — окремий кліп на доріжці «Svit Text»: посувай і розтягуй на таймлайні. Слова, шрифт, колір і розмір правиш у Fusion: вузол Text+ (SvText).": "Each line is its own clip on the “Svit Text” track: move and stretch it on the timeline. Edit words, font, colour and size in Fusion: the Text+ node (SvText).",
    "Редагований Text+": "Editable Text+", "Картинкою": "As images",
    "Кожен рядок — картинка на доріжці «Svit Text»: виглядає точно як у перегляді, посувається й розтягується, але слова не редагуються.": "Each line is an image on the “Svit Text” track: looks exactly like the preview, can be moved and stretched, but the words can't be edited.",
    "Кожен рядок — справжній титр Text+ на доріжці «Svit Text»: посувай на таймлайні, слова, шрифт і колір правиш в Inspector. Один раз перетягни Effects → Titles → Text+ у Media Pool — Svit бере його як основу.": "Each line is a real Text+ title on the “Svit Text” track: move it on the timeline, edit words, font and colour in the Inspector. Drag Effects → Titles → Text+ into the Media Pool once — Svit uses it as the base.",
    "Перевірити": "Check", "Text+ у Media Pool: ще не перевіряв": "Text+ in Media Pool: not checked yet", "Перевіряю Media Pool…": "Checking the Media Pool…",
    "Text+ у Media Pool не знайдено. Edit → Effects → Toolbox → Titles → перетягни Text+ у Media Pool цього проєкту, потім натисни «Перевірити»": "Text+ not found in the Media Pool. Edit → Effects → Toolbox → Titles → drag Text+ into this project's Media Pool, then press Check",
    "Скопіювати журнал": "Copy log", "Скопіювати": "Copy", "Журнал скопійовано — встав у чат з Claude (⌘V)": "Log copied — paste it into the chat with Claude (⌘V)",
    "Не вдалося скопіювати — натисни «Відкрити журнал»": "Couldn't copy — press “Open log”",
    "Скасувати": "Cancel", "Скасовую…": "Cancelling…", "Монтаж скасовано": "Editing cancelled",
    "Починаю…": "Starting…",
    "Слухаю слова": "Listening to words", "Шукаю найгучніші моменти": "Finding the loudest moments",
    "Дивлюсь кадри": "Looking at frames", "Вивчаю референси": "Studying references",
    "Монтую": "Editing", "Вношу правки": "Applying edits", "Вношу правки…": "Applying edits…",
    "Збираю таймлайн у DaVinci": "Building the timeline in DaVinci",
    "Оновлюю таймлайн у DaVinci": "Updating the timeline in DaVinci",
    "Готуюсь до аналізу": "Preparing the analysis", "Рахую точну ціну": "Calculating the exact price",
    "Слухаю музику: темп і удари": "Listening to the music: tempo and beats",
    "Завантажую модель розпізнавання мови": "Downloading the speech recognition model",
    "Створюю таймлайн": "Creating the timeline", "Ставлю ролики на експорт": "Queuing videos for export",
    // готово
    "ГОТОВО": "DONE", "Готово!": "Done!", "Готово": "Done",
    "Журнал роботи": "Work log",
    "— якщо щось вийшло не так, відкрий і надішли Claude": "— if something went wrong, open it and send it to Claude",
    "Що змінити?": "What to change?",
    "Напиши правку словами — Claude змінить план, а в DaVinci з'явиться нова версія таймлайну (попередня залишиться для порівняння). Правки дешеві: матеріал уже проаналізований.": "Write the change in words — Claude changes the plan, and a new timeline version appears in DaVinci (the previous one stays for comparison). Edits are cheap: the footage is already analysed.",
    "Весь ролик": "Whole video", "Тільки ділянку": "Only a section",
    "Наприклад: другий ролик зроби довшим, менше зумів у третьому": "For example: make the second video longer, fewer zooms in the third",
    "Наприклад: другий ролик зроби довшим, прибери склейку на 0:12, менше зумів у третьому": "For example: make the second video longer, remove the cut at 0:12, fewer zooms in the third",
    "Що зробити з цією ділянкою? Можна порожньо — Claude сам підбере кращі кадри": "What to do with this section? Can be empty — Claude picks better shots itself",
    "Змінити": "Change",
    "Коротші шматки, швидший ритм": "Shorter pieces, faster rhythm", "Менше зумів": "Fewer zooms",
    "Сильніший початок": "Stronger opening", "Інший фінал — на кульмінації": "Different ending — on the climax",
    "Довші плани, спокійніше": "Longer shots, calmer",
    "Підписи для постів": "Post captions", "Новий монтаж": "New edit", "Закрити": "Close",
    "Скопійовано — встав у чат з Claude": "Copied — paste it into the chat with Claude",
    // помилка
    "Щось пішло не так": "Something went wrong", "Назад": "Back", "Технічні деталі": "Technical details",
    "Скопіювати деталі": "Copy details", "Відкрити журнал": "Open log",
    "Звіт про збій уже відкрито в TextEdit — скопіюй його і надішли Claude.": "The crash report is already open in TextEdit — copy it and send it to Claude.",
    "Ключ Claude не підходить. Зміни його в налаштуваннях (шестерня вгорі).": "The Claude key doesn't work. Change it in settings (the gear at the top).",
    "На балансі Claude закінчились кошти. Поповни баланс і спробуй ще раз.": "Your Claude balance ran out. Top it up and try again.",
    "Забагато запитів до Claude. Зачекай хвилину і спробуй ще раз.": "Too many requests to Claude. Wait a minute and try again.",
    "Claude зараз перевантажений. Спробуй за кілька хвилин.": "Claude is overloaded right now. Try again in a few minutes.",
    "Немає з'єднання з інтернетом.": "No internet connection.", "Немає зв'язку": "No connection",
    "Claude не повернув план. Спробуй ще раз або уточни запит.": "Claude didn't return a plan. Try again or refine the request.",
    "Поповни баланс": "Top up your balance", "Поповнити": "Top up",
    // налаштування
    "Налаштування": "Settings", "Ключ Claude": "Claude key", "не вставлено": "not set",
    "Токенів цього місяця": "Tokens this month", "Версія": "Version",
    "Змінити ключ": "Change key", "Витрати на сайті": "Spending on the website",
    "Оновлення": "Updates", "Перевірити оновлення": "Check for updates",
    "Остання версія ✓": "Latest version ✓", "У тебе остання версія": "You have the latest version",
    "Журнали": "Logs", "Папка журналів": "Logs folder",
    "Журнал відкрито в TextEdit": "Log opened in TextEdit", "Не вдалося відкрити журнал": "Couldn't open the log",
    "Тримати вікно поверх DaVinci": "Keep window on top of DaVinci",
    "Вікно завжди поверх DaVinci": "Window always on top of DaVinci", "Вікно більше не закріплене": "Window is no longer pinned",
    "Мова інтерфейсу": "Interface language",
    // оновлення
    "Svit Editor · оновлення": "Svit Editor · update", "Доступна нова версія": "A new version is available",
    "Що нового": "What's new", "Пізніше": "Later", "Спробувати ще": "Try again", "Перезапустити": "Restart",
    "Оновлення займе менше хвилини": "The update takes less than a minute", "Оновлюю…": "Updating…",
    "Перезапущу Svit Editor, щоб увімкнути нову версію": "I'll restart Svit Editor to turn on the new version",
    // вітання
    "Svit Editor · вітання": "Svit Editor · welcome", "Офіційне повідомлення": "Official announcement",
    "Привіт!": "Hello!", "Це": "This is the", "айтішники Бобогорохії": "IT folks of Bobogorokhia",
    "! Ми раді повідомити, що наше суспільство перейшло в епоху нових технологій!": "! We are pleased to announce that our society has entered the age of new technologies!",
    "І ми створили нову": "And we have created a new",
    "розумну машину для нарізання шматків плівки": "smart machine for cutting pieces of film",
    "Бобогорохія · відділ нових технологій": "Bobogorokhia · department of new technologies",
    "Почати різати": "Start cutting",
  };

  // складені рядки: [регулярний вираз, заміна]
  const PL = (n, one, many) => (Math.abs(n) === 1 ? one : many);
  const RX = [
    [/^Text\+ у Media Pool: знайдено «(.+)» ✓ — текст стане титрами Text\+$/, "Text+ in Media Pool: found “$1” ✓ — text will be Text+ titles"],
    [/^Позначено: (\d+) відео · (.+)$/, (m,n,r)=>`Marked: ${n} ${PL(+n,"video","videos")} · ${r}`],
    [/^Перегляд на кадрі з «(.+)» — без токенів$/, "Preview on a frame from “$1” — no tokens"],
    [/ефекти ляжуть на Adjustment Clip \((\d+)\)/, "effects go onto the Adjustment Clip ($1)"],
    [/це монтаж Svit — зуми й переходи збережу/, "this is a Svit edit — zooms and transitions are kept"],
    [/^Що нового у (.+)$/, "What's new in $1"],
    [/^(\d+) (рядок|рядки|рядків) · прив'яжу до треку «(.+)»$/, (m,n,_,t)=>`${n} ${PL(+n,"line","lines")} · will sync to “${t}”`],
    [/^(\d+) (рядок|рядки|рядків) · увімкни «Монтаж під аудіо» і вибери трек, щоб прив'язати$/, (m,n)=>`${n} ${PL(+n,"line","lines")} · turn on “Edit to audio” and pick a track to sync`],
    [/^Готово · оновлено шматків: (\d+)/, "Done · clips updated: $1"], [/ · з помилками: (\d+)/, " · errors: $1"],
    [/^Оновлюю вигляд · (\d+) з (\d+)/, "Updating look · $1 of $2"],
    [/^Оновлено · шматків: (\d+)/, "Updated · clips: $1"], [/ · пропущено: (\d+)/, " · skipped: $1"],
    [/^Шматки з власними Fusion-композиціями не чіпав: (\d+)/, "Left clips with their own Fusion compositions untouched: $1"],
    [/ · (\d+) (кліп|кліпи|кліпів) · рухай повзунки — зміни одразу в DaVinci/, (m,n)=>` · ${n} ${PL(+n,"clip","clips")} · move the sliders — changes go straight to DaVinci`],
    [/^(\d+) відео$/, (m, n) => `${n} ${PL(+n, "video", "videos")}`],
    [/^Готово · (\d+) відео$/, (m, n) => `Done · ${n} ${PL(+n, "video", "videos")}`],
    [/відео (\d+) з (\d+)/g, "video $1 of $2"],
    [/ · (\d+) з (\d+)$/, " · $1 of $2"],
    [/Монтую ролик (\d+) з (\d+)/, "Editing video $1 of $2"],
    [/Монтую ще (\d+) відео/, "Editing $1 more videos"],
    [/Монтую · склейок: (\d+)/, "Editing · cuts: $1"],
    [/склейок: (\d+)/, "cuts: $1"],
    [/ · ще раз$/, " · once more"],
    [/переглядаю матеріал/, "reviewing the footage"],
    [/обираю найкращі моменти/, "picking the best moments"],
    [/вибудовую ритм і структуру/, "building rhythm and structure"],
    [/розставляю склейки/, "placing the cuts"],
    [/^разом /, "total "], [/ · найдовше /, " · longest "],
    [/(\d+) год (\d+) хв/, "$1 h $2 min"], [/(\d+) хв (\d+) с/, "$1 min $2 s"], [/(\d+) хв(?![А-Яа-яІіЇїЄєҐґ])/g, "$1 min"], [/(\d+) год(?![А-Яа-яІіЇїЄєҐґ])/g, "$1 h"],
    [/(\d+) с(?![А-Яа-яІіЇїЄєҐґ])/g, "$1 s"],
    [/^~(.+) роботи · /, "~$1 of work · "],
    [/ кадр\. · спалах /, " frames · flash "],
    [/^до ±/, "up to ±"],
    [/^Витрачено/, "Spent"], [/·\s*цього місяця /, "· this month "], [/ · таймлайн уже в DaVinci/, " · timeline is already in DaVinci"],
    [/ · нова версія таймлайну вже в DaVinci/, " · the new timeline version is already in DaVinci"],
    [/^Коментар монтажера: /, "Editor's note: "],
    [/^У DaVinci: шматків (\d+), з Fusion (\d+) \(за планом мало бути (\d+)\)\./, "In DaVinci: $1 pieces, $2 with Fusion (plan expected $3)."],
    [/^Правку внесено · версія /, "Edit applied · version "],
    [/^весь ролик · /, "whole video · "], [/^ділянка /, "section "],
    [/нормальна динаміка/, "normal pace"], [/швидка динаміка/, "fast pace"], [/повільна динаміка/, "slow pace"],
    [/кадрування \+ динамічний зум/, "framing + dynamic zoom"], [/\bкадрування\b/, "framing"], [/динамічний зум/, "dynamic zoom"],
    [/без зумів/, "no zoom"], [/без ефектів/, "no effects"], [/без переходів/, "no transitions"],
    [/ефектів: (\d+)/, "effects: $1"], [/переходів: (\d+)/, "transitions: $1"], [/абстракція (\d+)%/, "abstraction $1%"],
    [/автоконтраст/, "auto contrast"], [/вінтаж: авто/, "vintage: auto"], [/вінтаж: /, "vintage: "],
    [/дрімі (\d+)%/, "dreamy $1%"], [/розмиття (\d+)%/, "blur $1%"],
    [/^Синхронізую дублі з піснею/, "Syncing takes with the song"],
    [/^Слухаю «(.+)»…$/, "Listening to “$1”…"],
    [/^Додано: /, "Added: "], [/ — можна додати ще/, " — you can add more"], [/ — шукаю в Media Pool/, " — looking in the Media Pool"],
    [/^Доступна версія /, "Version available: "], [/^Доступна /, "Available "], [/^Зараз у тебе /, "You have "], [/^У тебе /, "You have "],
    [/^Оновлюю до /, "Updating to "], [/^Оновлено до /, "Updated to "],
    [/ · оновлення займе менше хвилини/, " · the update takes less than a minute"],
    [/^підключено …/, "connected …"],
    [/(\d+) (кліп|кліпи|кліпів)\b/, (m, n) => `${n} ${PL(+n, "clip", "clips")}`],
    [/(\d+) (файл|файли|файлів)\b/, (m, n) => `${n} ${PL(+n, "file", "files")}`],
    [/(\d+) (скрін|скріни|скрінів)\b/, (m, n) => `${n} ${PL(+n, "screenshot", "screenshots")}`],
    [/(\d+) (референс|референси|референсів)\b/, (m, n) => `${n} ${PL(+n, "reference", "references")}`],
    [/Трек не знайдено/, "Track not found"],
    [/джерело (\d+): /, "source $1: "],
  ];

  let lang = "uk";
  const orig = new WeakMap();          // вузол → оригінальний український текст
  const origAttr = new WeakMap();
  const ATTRS = ["placeholder", "data-tip", "title"];
  const CYR = /[А-Яа-яІіЇїЄєҐґ]/;

  function tr(s) {
    if (!s || !CYR.test(s)) return s;
    const lead = s.match(/^\s*/)[0], trail = s.match(/\s*$/)[0];
    const core = s.trim();
    if (EN[core] !== undefined) return lead + EN[core] + trail;
    let out = core;
    for (const [re, rep] of RX) out = out.replace(re, rep);
    // частини, розділені « · », перекладаємо окремо
    if (CYR.test(out) && out.includes(" · ")) out = out.split(" · ").map(p => EN[p.trim()] !== undefined ? EN[p.trim()] : p).join(" · ");
    return lead + out + trail;
  }

  function skip(node) {
    const el = node.nodeType === 1 ? node : node.parentElement;
    return !el || el.closest(".noi, script, style, textarea");
  }
  function skipAttr(el) { return !el || el.closest(".noi, script, style") }

  function apply(root) {
    if (!root) return;
    if (root.nodeType === 3) { doText(root); return }
    if (root.nodeType !== 1 || skipAttr(root)) return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n; while ((n = w.nextNode())) doText(n);
    const els = [root, ...root.querySelectorAll("*")];
    for (const el of els) { if (skipAttr(el)) continue; for (const a of ATTRS) doAttr(el, a) }
  }

  function doText(n) {
    if (skip(n)) return;
    const cur = n.nodeValue;
    if (lang === "en") {
      if (!CYR.test(cur)) return;
      orig.set(n, cur);
      const t = tr(cur);
      if (t !== cur) n.nodeValue = t;
    } else if (orig.has(n)) {
      n.nodeValue = orig.get(n); orig.delete(n);
    }
  }

  function doAttr(el, a) {
    if (!el.hasAttribute(a)) return;
    let m = origAttr.get(el); if (!m) { m = {}; origAttr.set(el, m) }
    const cur = el.getAttribute(a);
    if (lang === "en") {
      if (!CYR.test(cur)) return;
      m[a] = cur; const t = tr(cur); if (t !== cur) el.setAttribute(a, t);
    } else if (m[a] !== undefined) { el.setAttribute(a, m[a]); delete m[a] }
  }

  let obs = null, busy = false;
  function watch() {
    if (obs) return;
    obs = new MutationObserver(muts => {
      if (busy || lang !== "en") return;
      busy = true;
      try {
        for (const m of muts) {
          if (m.type === "characterData") doText(m.target);
          else if (m.type === "attributes") { if (!skipAttr(m.target)) doAttr(m.target, m.attributeName) }
          else m.addedNodes.forEach(apply);
        }
      } finally { busy = false }
    });
    obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }

  window.I18N = {
    get lang() { return lang },
    t: s => (lang === "en" ? tr(s) : s),
    set(l) {
      lang = l === "en" ? "en" : "uk";
      document.documentElement.lang = lang === "en" ? "en" : "uk";
      busy = true;
      try {
        if (lang === "en") { apply(document.body); watch() }
        else {
          const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          let n; while ((n = w.nextNode())) if (orig.has(n)) { n.nodeValue = orig.get(n); orig.delete(n) }
          document.querySelectorAll("*").forEach(el => ATTRS.forEach(a => doAttr(el, a)));
        }
      } finally { busy = false }
    },
  };
})();
