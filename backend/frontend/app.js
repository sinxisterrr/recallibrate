const buttons = document.querySelectorAll('[data-theme-btn]')
const pill = document.querySelector('.pill')
const connectBtn = document.getElementById('connect-btn')
const dbUrlInput = document.getElementById('db-url')

buttons.forEach((button) => {
    button.addEventListener('click', () => {
        const theme = button.dataset.themeBtn
        const index = [...buttons].indexOf(button)
        pill.style.transform = `translateX(${index * 100}%)` 
        document.documentElement.setAttribute('data-theme', theme)
    })
})

connectBtn.addEventListener('click', async () => {
    const url = dbUrlInput.value
    const res = await fetch(`http://localhost:8000/api/tables?db_url=${url}`)
    const data = await res.json()
    console.log(data)
    const tablesSection = document.getElementById('tables')
        tablesSection.innerHTML = ''

    data.tables.forEach((table) => {
        const button = document.createElement('button')
        button.className = 'tables-btn'
        button.textContent = table
        tablesSection.appendChild(button)
            button.addEventListener('click', async () => {
                const table = button.textContent
                const res = await fetch(`http://localhost:8000/api/tables/${table}/columns?db_url=${dbUrlInput.value}`)
                const data = await res.json()
                console.log(data)
                const searchSection = document.getElementById('search')
                searchSection.innerHTML = ''
                data.columns.forEach((col) => {
                    const label = document.createElement('label')
                    label.textContent = col.name
                    searchSection.appendChild(label)
                })
                document.querySelector('main').classList.add('table-view')
                document.getElementById('table-name').textContent = table
            })
    })

  })