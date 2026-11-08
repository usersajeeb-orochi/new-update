/* mascot_fun.js — extra activities for the character: meme moments, quotes, phone scrolling, tea breaks, umbrella, laptop, hype and more.
   The lines are built in (no internet). Add your own in Settings > Sajeeb > "Your own lines". Switch off: Settings > Sajeeb > Memes & quotes. */
(function () {
  "use strict";
  if (!window.RIKO || !window.C) return;
  const RK = RIKO, HK = RK.hooks, K = RK.core;
  let cfg = {}, lang = "en", lastAt = 0; const recent = [];
  const pick = (a) => { for (let i = 0; i < 6; i++) { const x = a[Math.floor(Math.random() * a.length)]; if (recent.indexOf(x) < 0) { recent.push(x); if (recent.length > 40) recent.shift(); return x; } } return a[Math.floor(Math.random() * a.length)]; };
  

  const MEME = [
    "This is fine. 🔥 (the clip folder is on fire)", "No cap, that was a clean crop.", "Main character energy detected.", "Aura +100 for that save.",
    "It's giving… organised archive.", "Bro is cooking. Let him cook.", "POV: you found the page number on the first try.", "Certified clip-slayer. Slay.",
    "Delulu is the solulu… but still check the date.", "Rizz level: crop tool.", "Ctrl+S is my love language.", "Not me forgetting the page number again.",
    "Vibe check: passed. ✅", "Touch grass? After this clip.", "Stonks ↗ (the clip counter)", "Bruh. Moment.", "Skill issue? No — newspaper issue.",
    "Sigma grindset: save, save, save.", "NPC behaviour: pressing Ctrl+V and waiting.", "Cooked? The deadline is cooked. We're fine.",
    "Me: one more clip. Also me: 40 clips later.", "That's lowkey a banger of a headline.", "Respectfully, this ePaper layout is chaos.",
    "Soft life = auto-crop + coffee.", "Wait, it's all columns? Always has been. 🔫", "Task failed successfully.", "Ratio + you saved + no typos.",
    "Understood the assignment. 📝", "Go touch some keyboard, king.", "If it fits, it ships. (the clip, I mean)", "Hold on, let him clip.",
    "The page number said: 'I'm not even mad.'", "Plot twist: the news was in the next column.", "Rent is due, but so are the clips.",
    "Is this the real life? Is this just fantasy? … No, it's page B4.", "Emotional damage: unsaved clip. 💔", "One does not simply skip the category."
  ];
  const MEME_BN = [
    "ভাই, এইটা কি ঠিক আছে?", "মামা, ফোল্ডার ঠিক আছে তো?", "ক্লিপ করা কঠিন না, পেজ নম্বর মনে রাখাই কঠিন!", "আজকে তো একদম পিকচার পারফেক্ট!",
    "দোস্ত, সেভ করেছিস তো? নাকি আবার ভুলে গেলি?", "চিল ব্রো, ডেডলাইন তো আছেই।", "এই না হলে আমার বস!", "বাহ! ক্রপ দেখে মনটা ভরে গেল।",
    "আরে ভাই, শুধু Ctrl+V চাপলে হবে না, ক্যাটাগরিও দিতে হয়!", "ব্যস্ত? নাকি ব্যস্ত থাকার অভিনয়?", "লাইফ ইজ শর্ট, ক্লিপ ইজ লং।", "চা না খেলে ক্লিপ হয় না, বুঝলে?",
    "ওস্তাদ, আজকে তো আগুন জ্বালাচ্ছেন!", "টেনশন নাই, আমি আছি।", "একটু পানি খাও, তারপর আবার যুদ্ধ!"
  ];
  const QUOTE = [
    "“Well begun is half done.” — Aristotle", "“The secret of getting ahead is getting started.” — Mark Twain", "“Quality is not an act, it is a habit.” — Will Durant",
    "“Do the next right thing.”", "“Small steps every day.”", "“It always seems impossible until it's done.” — Nelson Mandela",
    "“Don't watch the clock; do what it does. Keep going.” — Sam Levenson", "“Focus on being productive, not busy.” — Tim Ferriss",
    "“Done is better than perfect.”", "“You don't have to be great to start, but you have to start to be great.” — Zig Ziglar",
    "“Slow is smooth, smooth is fast.”", "“Energy flows where attention goes.”", "“Action is the foundational key to all success.” — Picasso",
    "“Make each day your masterpiece.” — John Wooden", "“The best way out is always through.” — Robert Frost", "“Consistency beats intensity.”",
    "“A journey of a thousand miles begins with a single step.” — Lao Tzu", "“What you do today can improve all your tomorrows.” — Ralph Marston"
  ];
  const QUOTE_BN = [
    "“যে পরিশ্রম করে, সফলতা তারই।”", "“ধৈর্য্য ধরো, ক্লিপ হবেই।”", "“আজকের কাজ আজই করো।”", "“ছোট ছোট পদক্ষেপই বড় যাত্রার শুরু।”",
    "“থেমে যেও না, এগিয়ে চলো।”", "“সময়ের এক ফোঁড় অসময়ের দশ ফোঁড়।”", "“কাজ শেষ হলে চায়ের বিরতি পাওনা।”", "“অভ্যাসই সাফল্যের চাবিকাঠি।”"
  ];
  const PHONE = ["Just checking the news… for work. 📱", "Doomscrolling? No. Research.", "Reading the headlines so you don't have to.", "One more reel… (that's a lie)", "Ooh, trending. I mean, important.",
    "Replying to nobody in particular.", "Battery 12%. Same energy as me."];
  const PHONE_BN = ["একটু খবর দেখছি… কাজের জন্যই!", "রিল দেখছি না, রিসার্চ করছি।", "ফোনে চার্জ ১২%, আমারও তাই।"];
  const TEA = ["Tea break. ☕ Productivity loading…", "Chai > everything.", "Sip. Think. Clip.", "Hydration check. Hydrate!"];
  const TEA_BN = ["চা-বিরতি! ☕", "এক কাপ চা, তারপর আবার কাজ।", "চা খেলে মাথা খোলে।"];
  const RAIN = ["Umbrella up. Rain or no rain, the news must go on.", "Is it raining? Nope. I just like this umbrella.", "Cloudy with a chance of deadlines."];
  const LAPTOP = ["Typing very important things…", "Alt+Tab, Alt+Tab, Alt+Tab…", "Mr. Robot mode: on.", "Compiling… the next clip.", "Just a quick spreadsheet. A quick one."];
  const HYPE = ["Let's goooo! 🚀", "We're on a roll!", "Clip. Save. Repeat. Legend.", "Big day. Big clips.", "Another one! (DJ Khaled voice)"];
  const HYPE_BN = ["চলো চলো, থেমো না!", "আজকে সব ক্লিপ আমাদের!", "দারুণ চলছে!"];
  const WAVE = ["Hi there! 👋", "Hey boss!", "Still here. Still cute.", "You look productive today."];
  const WAVE_BN = ["হাই! 👋", "কেমন আছো বস?", "আজকে তোমাকে দারুণ লাগছে!"];
  const SIT = ["Taking a seat. Standing is overrated.", "Legs: tired. Spirit: unbothered.", "Sitting. Thinking. Sitting again."];
  const HUG = ["Cat hug break. Don't tell the others.", "Emotional support plushie: online.", "Recharging with a hug."];
  const SAD = ["Nobody asked how I'm doing. (It's fine.)", "Missing the golden age of the print newspaper…", "Pour one out for the unsaved clip."];

  const pickLang = (en, bn) => { if (bn && (lang === "bn" || (lang === "mix" && Math.random() < .5))) return pick(bn); return pick(en); };
  const POSES = (a) => a.filter(p => p);
  // each activity: [weight, pose, seconds, mood, line source]
  const ACT = [
    [3, "wink", 4.5, "wink", () => pickLang(MEME, MEME_BN)], [3, "react", 4.5, "excited", () => pickLang(MEME, MEME_BN)], [2, "happy", 4.5, "happy", () => pickLang(MEME, MEME_BN)],
    [3, "tea", 6, "happy", () => pickLang(TEA, TEA_BN)], [2, "tea", 7, "wink", () => pickLang(QUOTE, QUOTE_BN)], [2, "laptop", 7, "wink", () => pick(QUOTE)],
    [3, "phone", 7, "cheeky", () => pickLang(PHONE, PHONE_BN)], [2, "laptop", 6, "cheeky", () => pick(LAPTOP)], [1.5, "umbrella", 6, "wink", () => pick(RAIN)],
    [2, "celebrate", 3.5, "excited", () => pickLang(HYPE, HYPE_BN)], [2, "wave", 3.5, "happy", () => pickLang(WAVE, WAVE_BN)], [1, "sitbox", 6, "happy", () => pick(SIT)],
    [1, "heart_hug", 5, "embarrassed", () => pick(HUG)], [.6, "sad", 4, "sad", () => pick(SAD)], [1.2, "paws", 5, "cheeky", () => pickLang(MEME, MEME_BN)]
  ];
  function perform() {
    if (!K.on || K.quiet || cfg.mascot_fun === false) return false;
    const have = (RK.skinSlots && RK.skinSlots()) || null;
    const list = ACT.filter(a => !have || have[a[1]]);
    if (!list.length) return false;
    let r = Math.random() * list.reduce((s, a) => s + a[0], 0), a = list[0];
    for (const x of list) { r -= x[0]; if (r <= 0) { a = x; break; } }
    K.setS("react", a[1], a[2]); K.say(a[4](), a[3], Math.max(3500, a[2] * 900));
    lastAt = Date.now(); return true;
  }
  HK.fun = perform;                                         // the character's decision loop calls this as one of its choices
  const old = HK.cfg;
  HK.cfg = (u) => { cfg = u || {}; lang = cfg.mascot_lang || "en"; old && old(u); };
  RK.fun = { perform, commands: [["Sajeeb: tell me a meme", () => { K.setS("react", "wink", 4); K.say(pickLang(MEME, MEME_BN), "cheeky", 6000); }],
    ["Sajeeb: quote of the moment", () => { K.setS("react", "tea", 6); K.say(pickLang(QUOTE, QUOTE_BN), "wink", 8000); }],
    ["Sajeeb: do something fun", () => perform()]] };
})();
