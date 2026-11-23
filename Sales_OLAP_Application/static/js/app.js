/**
 * PharmaTrack DW: Main Client Application Script
 * Bilingual Localization (English & Tamil), Accessibility Helpers,
 * and General Navigation Interactivity.
 */

(function() {
  // Bilingual Localization Dictionary (English & Tamil)
  const TRANSLATIONS = {
    en: {
      emergency_banner_text: "For life-threatening medical emergencies, call official national dispatch immediately:",
      nav_medicine: "🔍 Medicine Search",
      nav_pharmacy: "🏥 Pharmacy Finder",
      nav_hospital: "🚑 Hospital Finder",
      nav_emergency: "🚨 Emergency Help",
      nav_analytics: "📈 Demand & Weather",
      nav_schema: "📐 DWDM Warehouse & Schema",
      nav_etl: "⚙️ ETL Pipeline & Quality",
      nav_olap: "🧊 OLAP Cube",
      nav_organ: "🫀 Organ Donation Awareness"
    },
    ta: {
      emergency_banner_text: "உயிருக்கு ஆபத்தான அவசர சிகிச்சைகளுக்கு, உடனடியாக தேசிய அவசர எண்களை அழைக்கவும்:",
      nav_medicine: "🔍 மருந்து தேடல்",
      nav_pharmacy: "🏥 மருந்தகங்கள் கண்டறி",
      nav_hospital: "🚑 மருத்துவமனை கண்டறி",
      nav_emergency: "🚨 அவசர உதவி",
      nav_analytics: "📈 தேவை & காலநிலை பகுப்பாய்வு",
      nav_schema: "📐 DWDM தரவுக் கிடங்கு வரைபடம்",
      nav_etl: "⚙️ ETL குழாய் & தரத் தணிக்கை",
      nav_olap: "🧊 OLAP கனசதுரம்",
      nav_organ: "🫀 உறுப்பு தான விழிப்புணர்வு"
    }
  };

  function applyLanguage(lang) {
    const dict = TRANSLATIONS[lang] || TRANSLATIONS.en;
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (dict[key]) {
        el.innerText = dict[key];
      }
    });
    localStorage.setItem('pharmatrack_language', lang);
  }

  document.addEventListener('DOMContentLoaded', function() {
    // Language Switcher Initialization
    const langSelector = document.getElementById('lang-selector');
    if (langSelector) {
      const savedLang = localStorage.getItem('pharmatrack_language') || 'en';
      langSelector.value = savedLang;
      applyLanguage(savedLang);

      langSelector.addEventListener('change', function() {
        applyLanguage(this.value);
      });
    }

    // Auto-dismiss alert messages after 6 seconds
    setTimeout(() => {
      document.querySelectorAll('.flash-alert').forEach(alert => {
        alert.style.transition = 'opacity 0.5s ease';
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 500);
      });
    }, 6000);
  });
})();
