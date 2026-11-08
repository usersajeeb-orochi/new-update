// i18n: English + বাংলা.  Bangla drafted — correct any wording in this file.
window.I18N = {
  en: {
    commands:"Commands", nav_clip:"Clip", nav_tracker:"Tracker", nav_search:"Search", nav_subs:"Subs", nav_settings:"Settings",
    saving_to:"Saving to", categories:"Categories", paste:"Paste", empty_title:"Copy a clip from the ePaper",
    empty_sub:"It appears here by itself — or press Ctrl+V", apply_crop:"Apply suggested crop", layers:"Layers", adjust:"Image",
    header_h:"Header", show_header:"Show Page / Pos / Date line", logo_size:"Logo size", text_size:"Text size", quality:"Quality",
    auto_snatch:"Auto-grab copied images", auto_polish:"Auto polish on paste", pick_cat:"Pick a category", save:"Save",
    recent:"Recent saves", clips:"clips", saved:"saved", ready:"READY", undo:"Undo", saved_to:"Saved →",
    need_cat:"Pick a category first (press its quick-save key)", nothing:"Nothing to save — paste a clip first",
    general:"General", papers:"Newspapers", detection:"Detection", quicksave:"Quick-save keys", hotkeys:"Shortcuts", mapping:"Tab → paper rules",
    connections:"Connections", sync:"Sync", about:"About", ai_sec:"AI", pdefs:"Paper defaults", comfort:"Comfort & speed", riko:"Sajeeb", backups:"Backups", language:"Language", theme:"Theme", dark:"Dark", light:"Light",
    advanced:"Advanced", reset_builtin:"Reset to built-in", upload_now:"Upload now", lock_title:"Press the Telegram approval on your phone",
    waiting:"Waiting for approval…", granted:"Access granted", denied:"Access denied", update_ready:"Update ready",
    restart_update:"Restart & update now", end_title:"Upload today's work?", upload_now_b:"Upload now", next_time:"Next time", skip:"Skip",
    quit_confirm:"Close NAB?", categories_edit:"Edit categories", filter_trim:"Trim", filter_clean:"Clean", filter_pad:"Pad",
  },
  bn: {
    commands:"কমান্ড", nav_clip:"ক্লিপ", nav_tracker:"ট্র্যাকার", nav_search:"সার্চ", nav_subs:"সাবস্ক্রিপশন", nav_settings:"সেটিংস",
    saving_to:"সেভ হবে", categories:"ক্যাটাগরি", paste:"পেস্ট", empty_title:"ই-পেপার থেকে ক্লিপ কপি করুন",
    empty_sub:"এটি নিজে থেকেই এখানে আসবে — অথবা Ctrl+V চাপুন", apply_crop:"প্রস্তাবিত ক্রপ প্রয়োগ করুন", layers:"লেয়ার", adjust:"ছবি",
    header_h:"হেডার", show_header:"পেজ / পজিশন / তারিখ লাইন দেখান", logo_size:"লোগোর আকার", text_size:"লেখার আকার", quality:"কোয়ালিটি",
    auto_snatch:"কপি করা ছবি নিজে থেকে নিন", auto_polish:"পেস্টে অটো পলিশ", pick_cat:"ক্যাটাগরি বাছুন", save:"সেভ",
    recent:"সাম্প্রতিক সেভ", clips:"ক্লিপ", saved:"সেভ হয়েছে", ready:"প্রস্তুত", undo:"আনডু", saved_to:"সেভ হয়েছে →",
    need_cat:"আগে ক্যাটাগরি বাছুন (কুইক-সেভ কী চাপুন)", nothing:"সেভ করার কিছু নেই — আগে ক্লিপ পেস্ট করুন",
    general:"সাধারণ", papers:"পত্রিকা", detection:"ডিটেকশন", quicksave:"কুইক-সেভ কী", hotkeys:"শর্টকাট", mapping:"ট্যাব → পত্রিকা নিয়ম",
    connections:"কানেকশন", ai_sec:"এআই", sync:"সিঙ্ক", pdefs:"পত্রিকার ডিফল্ট", riko:"সাজিব", comfort:"আরাম ও গতি", backups:"ব্যাকআপ", about:"পরিচিতি", language:"ভাষা", theme:"থিম", dark:"ডার্ক", light:"লাইট",
    advanced:"অ্যাডভান্সড", reset_builtin:"বিল্ট-ইনে ফিরুন", upload_now:"এখনই আপলোড", lock_title:"ফোনে টেলিগ্রামে অনুমোদন দিন",
    waiting:"অনুমোদনের অপেক্ষায়…", granted:"অনুমতি দেওয়া হয়েছে", denied:"অনুমতি দেওয়া হয়নি", update_ready:"আপডেট প্রস্তুত",
    restart_update:"রিস্টার্ট করে আপডেট করুন", end_title:"আজকের কাজ আপলোড করবেন?", upload_now_b:"এখনই আপলোড", next_time:"পরের বার", skip:"বাদ দিন",
    quit_confirm:"NAB বন্ধ করবেন?", categories_edit:"ক্যাটাগরি সম্পাদনা", filter_trim:"ট্রিম", filter_clean:"ক্লিন", filter_pad:"প্যাড",
  }
};
window.LANG = "en";
window.t = function (k) { return (I18N[LANG] && I18N[LANG][k]) || I18N.en[k] || k; };
window.applyI18n = function (root) {
  (root || document).querySelectorAll("[data-i18n]").forEach(function (n) { n.textContent = t(n.getAttribute("data-i18n")); });
};
