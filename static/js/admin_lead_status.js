(function() {
    function colorize(select) {
        if (select.value === 'waiting_for_estimate') {
            select.style.color = 'red';
        } else {
            select.style.color = '';
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('select[name$="status"]').forEach(function(sel) {
            colorize(sel);
            sel.addEventListener('change', function() { colorize(sel); });
        });
    });
})();
