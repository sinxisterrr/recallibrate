const buttons = document.querySelectorAll('[data-theme-btn]')
const pill = document.querySelector('.pill')

buttons.forEach((button) => {
    button.addEventListener('click', () => {
        const theme = button.dataset.themeBtn
        const index = [...buttons].indexOf(button)
        pill.style.transform = `translateX(${index * 100}%)` 
        document.documentElement.setAttribute('data-theme', theme)
    })
})