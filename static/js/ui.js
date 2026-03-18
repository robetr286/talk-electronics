export function initUi(dom, callbacks = {}) {
    const { overlay, acceptWarningBtn, appContent, tabButtons, tabPanels } = dom;
    const { onShowApp = () => {}, onTabChanged = () => {} } = callbacks;

    if (acceptWarningBtn && overlay && appContent) {
        acceptWarningBtn.addEventListener('click', () => {
            overlay.style.display = 'none';
            appContent.classList.remove('hidden');
            onShowApp();
        });
    }

    if (tabButtons && tabPanels) {
        tabButtons.forEach((button) => {
            button.addEventListener('click', () => {
                if (button.classList.contains('active')) {
                    return;
                }

                const targetTab = button.dataset.tab;

                tabButtons.forEach((btn) => btn.classList.remove('active'));
                button.classList.add('active');

                tabPanels.forEach((panel) => {
                    const matches = panel.dataset.tabPanel === targetTab;
                    panel.classList.toggle('active', matches);
                });

                if (targetTab) {
                    onTabChanged(targetTab);
                }
            });
        });
    }
}
