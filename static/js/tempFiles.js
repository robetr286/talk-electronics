export function initTempFiles(dom, callbacks = {}) {
    const { cleanupBtn, tempFilesInfo } = dom;
    const { onCleanupSuccess = () => {} } = callbacks;
    const defaultStatusText = tempFilesInfo ? tempFilesInfo.textContent : '';
    let refreshTimeout = null;
    let originalButtonMarkup = cleanupBtn ? cleanupBtn.innerHTML : '';

    async function refreshNow() {
        if (!tempFilesInfo) {
            return;
        }

        try {
            const response = await fetch('/temp-files-info');
            const data = await response.json();

            if (data.count === 0) {
                tempFilesInfo.textContent = 'Brak';
                tempFilesInfo.classList.add('empty');
                if (cleanupBtn) {
                    cleanupBtn.disabled = true;
                }
            } else {
                tempFilesInfo.textContent = `${data.count} plik(ów), ${data.size_mb} MB`;
                tempFilesInfo.classList.remove('empty');
                if (cleanupBtn) {
                    cleanupBtn.disabled = false;
                }
            }
        } catch (error) {
            console.error('Error fetching temp files info:', error);
            tempFilesInfo.textContent = 'Błąd odczytu';
            tempFilesInfo.classList.remove('empty');
        }
    }

    function scheduleRefresh(delayMs) {
        if (refreshTimeout) {
            clearTimeout(refreshTimeout);
        }
        refreshTimeout = setTimeout(refreshNow, delayMs);
    }

    async function handleCleanup() {
        if (!cleanupBtn) {
            return;
        }

        originalButtonMarkup = cleanupBtn.innerHTML;
        cleanupBtn.disabled = true;
        cleanupBtn.innerHTML = '⏳ Czyszczenie...';

        try {
            const response = await fetch('/cleanup-temp', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
            });

            const data = await response.json();

            if (data.success) {
                cleanupBtn.innerHTML = `✅ Usunięto ${data.removed_count} plików (${data.freed_space_mb} MB)`;
                scheduleRefresh(2000);
                onCleanupSuccess();
            } else {
                cleanupBtn.innerHTML = '❌ Błąd';
                setTimeout(() => {
                    cleanupBtn.innerHTML = originalButtonMarkup;
                    cleanupBtn.disabled = false;
                }, 2000);
            }
        } catch (error) {
            console.error('Error cleaning up temp files:', error);
            cleanupBtn.innerHTML = '❌ Błąd połączenia';
            setTimeout(() => {
                cleanupBtn.innerHTML = originalButtonMarkup;
                cleanupBtn.disabled = false;
            }, 2000);
        }
    }

    if (cleanupBtn) {
        cleanupBtn.addEventListener('click', handleCleanup);
    }

    return {
        refreshNow,
        scheduleRefresh,
        resetStatus() {
            if (tempFilesInfo) {
                tempFilesInfo.textContent = defaultStatusText;
            }
            if (cleanupBtn) {
                cleanupBtn.innerHTML = originalButtonMarkup;
                cleanupBtn.disabled = true;
            }
        },
    };
}
