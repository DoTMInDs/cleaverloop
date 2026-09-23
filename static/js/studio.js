// CleaverLoop AI - Client-side Studio Interactions & Dialogue Synthesis Engine

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss Django messages after 5 seconds
    const alerts = document.querySelectorAll('.auto-dismiss-alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s ease';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });

    // Instant wake-up when user switches back to browser tab
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            const activePollers = document.querySelectorAll('[hx-trigger*="load delay"], [hx-trigger*="every"]');
            activePollers.forEach(el => {
                if (window.htmx) {
                    htmx.trigger(el, 'load');
                }
            });
        }
    });

    window.addEventListener('focus', () => {
        const activePollers = document.querySelectorAll('[hx-trigger*="load delay"], [hx-trigger*="every"]');
        activePollers.forEach(el => {
            if (window.htmx) {
                htmx.trigger(el, 'load');
            }
        });
    });
});

// Copy to clipboard helper
function copyToClipboard(text, element) {
    navigator.clipboard.writeText(text).then(() => {
        const originalText = element.innerText;
        element.innerText = 'Copied!';
        element.classList.add('text-emerald-400');
        setTimeout(() => {
            element.innerText = originalText;
            element.classList.remove('text-emerald-400');
        }, 2000);
    });
}

// Smart in-character dialogue generation engine (Client-side fallback)
function buildContextualDialogue(promptText, charName, durationSeconds, style = 'dialogue') {
    const raw = (promptText || '').toLowerCase();
    const name = charName || '';
    const duration = parseFloat(durationSeconds) || 5;
    const isShort = duration <= 6;

    if (style === 'foley') {
        const cleanScene = (promptText || 'urban scene')
            .replace(/cinematic|8k|4k|photorealistic|hyper-detailed|unreal engine|35mm|tracking shot|close-up|drone shot|render|masterpiece/gi, '')
            .trim();
        return `High-fidelity atmospheric foley, realistic environmental ambient sounds, footsteps, traffic, and subtle background score matching: ${cleanScene}`;
    }

    if (style === 'monologue') {
        if (raw.includes('interview') || raw.includes('cv') || raw.includes('certificate') || raw.includes('folder') || raw.includes('suit')) {
            return isShort
                ? `Stay sharp, ${name || 'Kwame'}... everything you've worked for comes down to this interview.`
                : `Stay focused, ${name || 'Kwame'}. You have the qualifications in hand, your mind is prepared, and today is the day you claim your future.`;
        }
        if (raw.includes('car') || raw.includes('suv') || raw.includes('luxury') || raw.includes('admire') || raw.includes('road')) {
            return isShort
                ? `Just watch... with enough discipline and hustle, that's going to be mine.`
                : `Look at that vehicle... remember this feeling, because soon enough, you'll be the one driving it through these streets.`;
        }
        if (raw.includes('walk') || raw.includes('street') || raw.includes('city') || raw.includes('accra') || raw.includes('market')) {
            return isShort
                ? `One step at a time... no looking back now.`
                : `Every step through this city brings me closer to where I need to be. The journey starts right here.`;
        }
        return isShort
            ? `Take a breath... time to make this moment count.`
            : `Keep your eyes on the goal. Every challenge is just preparation for the next big win.`;
    }

    // Default: First-person spoken line (Character talking directly)
    if (raw.includes('interview') || raw.includes('cv') || raw.includes('certificate') || raw.includes('folder') || raw.includes('suit') || raw.includes('job')) {
        return isShort
            ? "I've got all my certificates ready... today, I'm getting that job."
            : "I've organized every certificate in this folder. I'm ready to walk into this interview and show them what I'm capable of.";
    }

    if (raw.includes('car') || raw.includes('suv') || raw.includes('luxury') || raw.includes('admire') || raw.includes('road') || raw.includes('drive')) {
        return isShort
            ? "One day... that is going to be me behind that wheel."
            : "Look at that ride. With the hard work I'm putting in every day, I know I'll be driving one soon.";
    }

    if (raw.includes('walk') || raw.includes('street') || raw.includes('city') || raw.includes('accra') || raw.includes('tro-tro')) {
        return isShort
            ? "Stepping through this busy city... time to make things happen."
            : "Moving through these streets with pure focus. Today is all about progress and seeing my plans through.";
    }

    if (raw.includes('meeting') || raw.includes('office') || raw.includes('tech') || raw.includes('desk') || raw.includes('computer')) {
        return isShort
            ? "Let's review the final plan and build something incredible."
            : "We've got the strategy in place. Now let's execute with precision and deliver extraordinary results.";
    }

    if (raw.includes('success') || raw.includes('celebrat') || raw.includes('smile') || raw.includes('happy') || raw.includes('win')) {
        return isShort
            ? "We actually did it... all that effort was completely worth it!"
            : "Looking back at where we started, this moment feels amazing. We put in the work and achieved it.";
    }

    return isShort
        ? "Alright... time to step forward and make this happen."
        : "Everything is aligned. I'm taking this step with confidence and making every second count.";
}

// Alpine.js component helper for Generation Status Card
function generationStatusCard(videoDuration, promptText, charName) {
    const duration = parseFloat(videoDuration) || 5;
    const defaultFoley = buildContextualDialogue(promptText, charName, duration, 'foley');

    return {
        showAudioSynth: false,
        audioType: 'foley',
        audioPrompt: defaultFoley,
        selectedVoice: 'adam',
        videoDuration: duration,
        isPlayingSync: false,
        isDeducing: false,
        deducedEmotion: '',
        get wordCount() {
            return this.audioPrompt ? this.audioPrompt.trim().split(/\s+/).filter(Boolean).length : 0;
        },
        get estimatedSpokenSeconds() {
            return (this.wordCount / 2.3).toFixed(1);
        },
        get isDurationFitting() {
            return parseFloat(this.estimatedSpokenSeconds) <= (this.videoDuration + 0.6);
        },
        async setAudioType(type) {
            this.audioType = type;
            if (type === 'tts') {
                if (!this.audioPrompt || this.audioPrompt.startsWith('High-fidelity') || this.audioPrompt.startsWith('Cinematic') || this.audioPrompt.startsWith('Realistic')) {
                    await this.generateDialogue('dialogue');
                }
            } else if (type === 'foley') {
                if (!this.audioPrompt || this.audioPrompt.includes("I've") || this.audioPrompt.includes("I'm") || this.audioPrompt.includes("One day") || this.audioPrompt.includes("today")) {
                    await this.generateDialogue('foley');
                }
            }
        },
        async generateDialogue(style) {
            this.isDeducing = true;
            try {
                const csrftoken = getCookie('csrftoken') || document.querySelector('[name=csrfmiddlewaretoken]')?.value;
                const resp = await fetch('/generations/api/generate-dialogue/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrftoken,
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        prompt: promptText,
                        character_name: charName,
                        duration: this.videoDuration,
                        style: style
                    })
                });
                if (resp.ok) {
                    const data = await resp.json();
                    if (data.dialogue) {
                        this.audioPrompt = data.dialogue;
                        if (data.suggested_voice) {
                            this.selectedVoice = data.suggested_voice;
                        }
                        this.deducedEmotion = data.emotion || '';
                        this.isDeducing = false;
                        return;
                    }
                }
            } catch (e) {
                console.warn('AI dialogue deduction error, using local fallback:', e);
            }
            this.isDeducing = false;
            this.audioPrompt = buildContextualDialogue(promptText, charName, this.videoDuration, style);
        },
        init() {
            this.$nextTick(() => {
                const vid = this.$refs.videoElem;
                const aud = this.$refs.audioElem;
                if (vid && aud) {
                    vid.addEventListener('pause', () => { if (!vid.seeking) aud.pause(); this.isPlayingSync = false; });
                    vid.addEventListener('play', () => { if (this.isPlayingSync) aud.play(); });
                    vid.addEventListener('seeked', () => { aud.currentTime = vid.currentTime; });
                    vid.addEventListener('ended', () => { aud.pause(); aud.currentTime = 0; this.isPlayingSync = false; });
                    vid.addEventListener('timeupdate', () => {
                        if (vid.duration && aud.currentTime >= vid.duration) {
                            aud.pause();
                        }
                    });
                }
            });
        },
        toggleSyncPlay() {
            const vid = this.$refs.videoElem;
            const aud = this.$refs.audioElem;
            if (!vid || !aud) return;
            if (vid.paused) {
                aud.currentTime = vid.currentTime;
                vid.muted = true;
                vid.play();
                aud.play();
                this.isPlayingSync = true;
            } else {
                vid.pause();
                aud.pause();
                this.isPlayingSync = false;
            }
        }
    };
}

// Alpine.js component helper for Generation Detail Inspector
function generationDetailInspector(videoDuration, promptText, charName) {
    const duration = parseFloat(videoDuration) || 5;
    const defaultFoley = buildContextualDialogue(promptText, charName, duration, 'foley');

    return {
        audioType: 'foley',
        audioPrompt: defaultFoley,
        selectedVoice: 'adam',
        selectedVoiceName: 'Adam (Cinematic)',
        selectedVoiceDesc: 'Deep, cinematic male narrator',
        selectedVoiceBadge: 'Cinematic',
        selectedVoiceIsCloned: false,
        voiceDropdownOpen: false,
        voiceSearch: '',
        selectVoice(id, name, desc, badge, isCloned) {
            this.selectedVoice = id;
            this.selectedVoiceName = name;
            this.selectedVoiceDesc = desc || '';
            this.selectedVoiceBadge = badge || (isCloned ? 'CLONED' : 'PRESET');
            this.selectedVoiceIsCloned = !!isCloned;
            this.voiceDropdownOpen = false;
        },
        isPlayingSync: false,
        isDeducing: false,
        deducedEmotion: '',
        get wordCount() {
            return this.audioPrompt ? this.audioPrompt.trim().split(/\s+/).filter(Boolean).length : 0;
        },
        get estimatedSpokenSeconds() {
            return (this.wordCount / 2.3).toFixed(1);
        },
        get isDurationFitting() {
            return parseFloat(this.estimatedSpokenSeconds) <= (this.videoDuration + 0.6);
        },
        async setAudioType(type) {
            this.audioType = type;
            if (type === 'tts') {
                if (!this.audioPrompt || this.audioPrompt.startsWith('High-fidelity') || this.audioPrompt.startsWith('Cinematic') || this.audioPrompt.startsWith('Realistic')) {
                    await this.generateDialogue('dialogue');
                }
            } else if (type === 'foley') {
                if (!this.audioPrompt || this.audioPrompt.includes("I've") || this.audioPrompt.includes("I'm") || this.audioPrompt.includes("One day") || this.audioPrompt.includes("today")) {
                    await this.generateDialogue('foley');
                }
            }
        },
        async generateDialogue(style) {
            this.isDeducing = true;
            try {
                const csrftoken = getCookie('csrftoken') || document.querySelector('[name=csrfmiddlewaretoken]')?.value;
                const resp = await fetch('/generations/api/generate-dialogue/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrftoken,
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        prompt: promptText,
                        character_name: charName,
                        duration: this.videoDuration,
                        style: style
                    })
                });
                if (resp.ok) {
                    const data = await resp.json();
                    if (data.dialogue) {
                        this.audioPrompt = data.dialogue;
                        if (data.suggested_voice) {
                            this.selectedVoice = data.suggested_voice;
                        }
                        this.deducedEmotion = data.emotion || '';
                        this.isDeducing = false;
                        return;
                    }
                }
            } catch (e) {
                console.warn('AI dialogue deduction error, using local fallback:', e);
            }
            this.isDeducing = false;
            this.audioPrompt = buildContextualDialogue(promptText, charName, this.videoDuration, style);
        },
        init() {
            this.$nextTick(() => {
                const vid = this.$refs.videoPlayer;
                const aud = this.$refs.audioPlayer;
                if (vid && aud) {
                    vid.addEventListener('pause', () => { if (!vid.seeking) aud.pause(); this.isPlayingSync = false; });
                    vid.addEventListener('play', () => { if (this.isPlayingSync) aud.play(); });
                    vid.addEventListener('seeked', () => { aud.currentTime = vid.currentTime; });
                    vid.addEventListener('ended', () => { aud.pause(); aud.currentTime = 0; this.isPlayingSync = false; });
                    vid.addEventListener('timeupdate', () => {
                        if (vid.duration && aud.currentTime >= vid.duration) {
                            aud.pause();
                        }
                    });
                }
            });
        },
        toggleSyncPlay() {
            const vid = this.$refs.videoPlayer;
            const aud = this.$refs.audioPlayer;
            if (!vid || !aud) return;
            if (vid.paused) {
                aud.currentTime = vid.currentTime;
                vid.muted = true;
                vid.play();
                aud.play();
                this.isPlayingSync = true;
            } else {
                vid.pause();
                aud.pause();
                this.isPlayingSync = false;
            }
        }
    };
}
