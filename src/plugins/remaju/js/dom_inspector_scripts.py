DOM_INSPECTOR_SCRIPT = r"""
(() => {
    const spinner = document.querySelector('.spinner, .loading, .blockUI');
    const modal = document.querySelector('.modal.show, .sweet-alert.show');
    const btnCasilla = document.querySelector('button.btn-casilla, input[value="Con Casilla"]');
    const captchaError = document.body.innerText.includes('CAPTCHA incorrecto');
    return JSON.stringify({
        spinner_visible: Boolean(spinner),
        modal_visible: Boolean(modal),
        btn_casilla_active: Boolean(btnCasilla),
        captcha_error: captchaError
    });
})();
"""
